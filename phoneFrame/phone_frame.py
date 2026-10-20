#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pillow>=10"]
# ///
"""Put a phone frame around iOS or Android screenshots.

The frame is drawn here, sized to the screenshot, so no device art is needed: an iPhone with
a Dynamic Island or a notch, or an Android phone with a punch-hole camera. The platform and
the camera cutout are guessed from the screenshot's resolution (iPhone screenshots come in a
few fixed sizes, everything else is taken as Android); override them with --platform and
--cutout. Landscape screenshots get a landscape frame.

Instead of the drawn frame, --mockup takes a design-tool SVG export (Figma's, for example)
of a device frame with one screen in it: two rects filled with embedded PNGs, the screen
first and the frame on top. The screenshot goes where the screen was, under the frame.

Usage: phone_frame.py shot.png [more.png ...] [-o out.png | --out-dir DIR]
                      [--platform auto|ios|android] [--cutout auto|island|notch|hole|none]
                      [--color '#2c2c2e'] [--width 1000] [--background '#ffffff']
                      [--mockup frame.svg] [--radius 0.14]
Writes <name>-framed.png next to each screenshot unless told otherwise.
"""

import argparse
import base64
import io
import re
import sys
from pathlib import Path

from PIL import Image, ImageColor, ImageDraw

SS = 3  # supersampling for smooth edges on the drawn frame

# Portrait iPhone screenshot sizes and the cutout each device has.
IOS_SIZES = {
    **dict.fromkeys([(1179, 2556), (1290, 2796), (1206, 2622), (1320, 2868), (1260, 2736)], 'island'),
    **dict.fromkeys([(1125, 2436), (1242, 2688), (828, 1792), (1170, 2532), (1284, 2778), (1080, 2340)], 'notch'),
    **dict.fromkeys([(750, 1334), (1242, 2208), (640, 1136)], 'none'),
}

# Everything as a fraction of the screen's width, so it holds at any resolution.
# radius: screen corner; bezel: black border; rim: metal edge outside it;
# buttons: (side, top, bottom) as fractions of the device's height.
PLATFORMS = {
    'ios': dict(
        radius=0.145, bezel=0.042, rim=0.014, color='#2c2c2e', sheen='#76767c',
        buttons=[('left', 0.165, 0.205), ('left', 0.255, 0.32), ('left', 0.345, 0.41), ('right', 0.27, 0.39)],
    ),
    'android': dict(
        radius=0.085, bezel=0.034, rim=0.010, color='#1d1d1f', sheen='#4a4a4f',
        buttons=[('right', 0.21, 0.27), ('right', 0.33, 0.45)],
    ),
}
BUTTON_DEPTH = 0.009


def guess(size, platform, cutout):
    portrait = tuple(sorted(size))
    if platform == 'auto':
        platform = 'ios' if portrait in IOS_SIZES else 'android'
    if cutout == 'auto':
        cutout = IOS_SIZES.get(portrait, 'island') if platform == 'ios' else 'hole'
    return platform, cutout


def rounded_mask(size, radius, scale=SS):
    """An antialiased rounded-rect alpha mask."""
    w, h = size
    big = Image.new('L', (w * scale, h * scale), 0)
    ImageDraw.Draw(big).rounded_rectangle((0, 0, w * scale - 1, h * scale - 1), radius * scale, fill=255)
    return big.resize(size, Image.LANCZOS)


def draw_frame(shot, platform, cutout, color, radius):
    """The screenshot inside a drawn phone, on a transparent canvas just big enough for it."""
    spec = PLATFORMS[platform]
    landscape = shot.width > shot.height
    if landscape:  # frame it upright, with the camera on the left edge, then turn it back
        shot = shot.rotate(-90, expand=True)
    w, h = shot.size
    r = (spec['radius'] if radius is None else radius) * w
    if cutout == 'none' and radius is None:
        r = 0.02 * w
    bezel, rim, depth = spec['bezel'] * w, spec['rim'] * w, BUTTON_DEPTH * w
    edge = bezel + rim
    pad = edge + depth
    cw, ch = round(w + 2 * pad), round(h + 2 * pad)
    ox = oy = round(pad)  # screen origin on the canvas

    s = SS
    frame = Image.new('RGBA', (cw * s, ch * s), (0, 0, 0, 0))
    d = ImageDraw.Draw(frame)
    metal = ImageColor.getrgb(color or spec['color'])
    sheen = ImageColor.getrgb(spec['sheen'])

    # Side buttons, poking out past the rim.
    body_top, body_h = oy - edge, h + 2 * edge
    for side, a, b in spec['buttons']:
        y0, y1 = body_top + a * body_h, body_top + b * body_h
        x0 = ox - edge - depth if side == 'left' else ox + w + edge - depth
        d.rounded_rectangle([x0 * s, y0 * s, (x0 + 2 * depth) * s, y1 * s], depth * s, fill=metal)

    # Metal body, a thin sheen line just inside its edge, then the black bezel.
    body = [(ox - edge) * s, (oy - edge) * s, (ox + w + edge) * s, (oy + h + edge) * s]
    d.rounded_rectangle(body, (r + edge) * s, fill=metal)
    inset = rim * 0.35 * s
    d.rounded_rectangle([body[0] + inset, body[1] + inset, body[2] - inset, body[3] - inset],
                        (r + edge) * s - inset, outline=sheen, width=max(1, round(rim * 0.18 * s)))
    d.rounded_rectangle([(ox - bezel) * s, (oy - bezel) * s, (ox + w + bezel) * s, (oy + h + bezel) * s],
                        (r + bezel) * s, fill='black')

    frame = frame.resize((cw, ch), Image.LANCZOS)

    # The screenshot, cut to the display's corners (a pixel wider than the bezel's opening so
    # no light seam shows between them), then the camera cutout drawn over it.
    canvas = Image.new('RGBA', (cw, ch), (0, 0, 0, 0))
    canvas.alpha_composite(frame)
    canvas.paste(shot.convert('RGBA'), (ox, oy), rounded_mask((w, h), r))

    top = Image.new('RGBA', (cw * s, ch * s), (0, 0, 0, 0))
    d = ImageDraw.Draw(top)
    cx = (ox + w / 2) * s
    if cutout == 'island':
        iw, ih, it = 0.322 * w, 0.095 * w, 0.03 * w
        d.rounded_rectangle([cx - iw / 2 * s, (oy + it) * s, cx + iw / 2 * s, (oy + it + ih) * s], ih / 2 * s, fill='black')
    elif cutout == 'notch':
        # Part of the bezel: flat on top, rounded below, flaring into the screen's top edge.
        nw, nh, nr, ear = 0.42 * w, 0.085 * w, 0.05 * w, 0.02 * w
        x0, x1 = cx - nw / 2 * s, cx + nw / 2 * s
        d.rounded_rectangle([x0, (oy - 1) * s, x1, (oy + nh) * s], nr * s, fill='black',
                            corners=(False, False, True, True))
        for x, sign in ((x0, -1), (x1, 1)):
            outer = x + sign * ear * s
            d.rectangle([min(x, outer), oy * s, max(x, outer), (oy + ear) * s], fill='black')
            d.ellipse([outer - ear * s, oy * s, outer + ear * s, (oy + 2 * ear) * s], fill=(0, 0, 0, 0))
    elif cutout == 'hole':
        hd, hc = 0.042 * w, 0.055 * w
        d.ellipse([cx - hd / 2 * s, (oy + hc - hd / 2) * s, cx + hd / 2 * s, (oy + hc + hd / 2) * s], fill='black')
    canvas.alpha_composite(top.resize((cw, ch), Image.LANCZOS))

    return canvas.rotate(90, expand=True) if landscape else canvas


def load_mockup(path):
    """The frame picture and where the screen sits in it, in the picture's own pixels."""
    svg = Path(path).read_text()
    rects = [tuple(map(float, m.groups())) for m in re.finditer(
        r'<rect x="([\d.]+)" y="([\d.]+)" width="([\d.]+)" height="([\d.]+)"[^>]*fill="url\(#', svg)]
    images = [base64.b64decode(m.group(1)) for m in re.finditer(
        r'<image [^>]*(?:xlink:)?href="data:image/png;base64,([^"]+)"', svg)]
    if len(rects) < 2 or len(images) < 2:
        sys.exit(f'{path}: expected two image-filled rects (screen, then frame); found {len(rects)} rects, {len(images)} images')
    screen, outer = rects[0], rects[-1]
    frame = Image.open(io.BytesIO(images[-1])).convert('RGBA')
    sx, sy = frame.width / outer[2], frame.height / outer[3]
    box = (round((screen[0] - outer[0]) * sx), round((screen[1] - outer[1]) * sy),
           round(screen[2] * sx), round(screen[3] * sy))
    return frame, box


def mockup_frame(shot, frame, box, radius):
    left, top, w, h = box
    if abs(shot.width / shot.height - w / h) > 0.02:
        print(f'warning: screenshot is {shot.width}x{shot.height}, the mock-up screen {w}x{h}; it will be stretched',
              file=sys.stderr)
    canvas = Image.new('RGBA', frame.size, (0, 0, 0, 0))
    canvas.paste(shot.convert('RGBA').resize((w, h), Image.LANCZOS), (left, top), rounded_mask((w, h), radius * w))
    canvas.alpha_composite(frame)
    return canvas


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('shots', nargs='+', type=Path, help='screenshots (PNG or JPEG)')
    ap.add_argument('-o', '--out', type=Path, help='output file (one screenshot only)')
    ap.add_argument('--out-dir', type=Path, help='write <name>-framed.png here instead of next to each screenshot')
    ap.add_argument('--platform', choices=['auto', 'ios', 'android'], default='auto')
    ap.add_argument('--cutout', choices=['auto', 'island', 'notch', 'hole', 'none'], default='auto')
    ap.add_argument('--color', help="frame's metal colour, e.g. '#e3d9c6' (default: dark grey)")
    ap.add_argument('--radius', type=float, help="screen corner radius as a fraction of the screen's width")
    ap.add_argument('--width', type=int, help='scale the result to this many pixels wide')
    ap.add_argument('--background', help='fill the transparent surround with this colour')
    ap.add_argument('--mockup', type=Path, help='use the frame from this SVG export instead of drawing one')
    args = ap.parse_args()
    if args.out and len(args.shots) > 1:
        ap.error('-o takes one screenshot; use --out-dir for several')

    mockup = load_mockup(args.mockup) if args.mockup else None
    for path in args.shots:
        shot = Image.open(path)
        platform, cutout = guess(shot.size, args.platform, args.cutout)
        if mockup:
            radius = PLATFORMS[platform]['radius'] if args.radius is None else args.radius
            out = mockup_frame(shot, *mockup, radius)
        else:
            out = draw_frame(shot, platform, cutout, args.color, args.radius)
        if args.width:
            out = out.resize((args.width, round(out.height * args.width / out.width)), Image.LANCZOS)
        if args.background:
            bg = Image.new('RGBA', out.size, args.background)
            bg.alpha_composite(out)
            out = bg.convert('RGB')
        dest = args.out or (args.out_dir or path.parent) / f'{path.stem}-framed.png'
        dest.parent.mkdir(parents=True, exist_ok=True)
        out.save(dest)
        print(f'{dest}  ({platform}, {"mockup" if mockup else cutout}, {out.width}x{out.height})')


if __name__ == '__main__':
    main()
