#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pillow>=10.1"]
# ///
"""Put images side by side with labels, to compare variants or a before and after.

Each image is scaled to the same height and labelled (with its file name unless --labels
says otherwise). --zoom adds a row of enlarged crops of the same region of every image, for
details too small to judge at full size. --diff, with exactly two images of the same size,
adds a third tile with the pixels that changed in red over a faded copy, and prints how many
changed.

Usage: compare_images.py a.png b.png [...] [-o compare.png] [--labels A B ...] [--cols N]
                         [--height 900] [--zoom x,y,w,h] [--diff] [--background '#ececef']
--zoom takes pixels of the original images, or fractions of their size (0.2,0,0.6,0.1).
"""

import argparse
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageColor, ImageDraw, ImageFont

GAP = 32


def font(size):
    return ImageFont.load_default(size=size)


def flatten(img, background):
    """The image over the background, so transparent parts don't turn black."""
    img = img.convert('RGBA')
    bg = Image.new('RGBA', img.size, background)
    bg.alpha_composite(img)
    return bg.convert('RGB')


def crop_box(spec, size):
    try:
        x, y, w, h = (float(v) for v in spec.split(','))
    except ValueError:
        sys.exit(f'--zoom takes x,y,w,h, not {spec!r}')
    if max(x, y, w, h) <= 1:  # fractions of the image
        x, w = x * size[0], w * size[0]
        y, h = y * size[1], h * size[1]
    box = (round(x), round(y), round(min(x + w, size[0])), round(min(y + h, size[1])))
    if box[2] <= box[0] or box[3] <= box[1]:
        sys.exit(f'--zoom {spec} is outside a {size[0]}x{size[1]} image')
    return box


def diff_tile(a, b):
    if a.size != b.size:
        sys.exit(f'--diff needs images of the same size; got {a.size[0]}x{a.size[1]} and {b.size[0]}x{b.size[1]}')
    changed = ImageChops.difference(a, b).convert('L').point(lambda v: 255 if v > 8 else 0)
    share = sum(changed.histogram()[255:]) / (a.width * a.height)
    faded = Image.blend(a.convert('L').convert('RGB'), Image.new('RGB', a.size, 'white'), 0.6)
    faded.paste(Image.new('RGB', a.size, (230, 30, 40)), mask=changed)
    return faded, share


def sheet(tiles, labels, cols, background, label_size):
    """Tiles in a grid, each with its label underneath."""
    rows = [tiles[i:i + cols] for i in range(0, len(tiles), cols)]
    label_rows = [labels[i:i + cols] for i in range(0, len(labels), cols)]
    cell_w = max(t.width for t in tiles)
    label_h = round(label_size * 1.8) if any(labels) else 0
    heights = [max(t.height for t in row) for row in rows]
    w = GAP + len(rows[0]) * (cell_w + GAP)
    h = GAP + sum(rh + label_h + GAP for rh in heights)
    out = Image.new('RGB', (w, h), background)
    draw = ImageDraw.Draw(out)
    f = font(label_size)
    ink = '#222' if sum(ImageColor.getrgb(background)[:3]) > 380 else '#eee'
    y = GAP
    for row, row_labels, rh in zip(rows, label_rows, heights):
        for i, (tile, label) in enumerate(zip(row, row_labels)):
            x = GAP + i * (cell_w + GAP)
            out.paste(tile, (x + (cell_w - tile.width) // 2, y + (rh - tile.height) // 2))
            if label:
                draw.text((x + cell_w / 2, y + rh + label_h / 2), label, fill=ink, font=f, anchor='mm')
        y += rh + label_h + GAP
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('images', nargs='+', type=Path)
    ap.add_argument('-o', '--out', type=Path, default=Path('compare.png'))
    ap.add_argument('--labels', nargs='+', help='one per image (default: file names)')
    ap.add_argument('--cols', type=int, help='images per row (default: all in one row)')
    ap.add_argument('--height', type=int, help='scale every image to this height (default: the smallest, at most 900)')
    ap.add_argument('--zoom', help='add enlarged crops of this region: x,y,w,h in pixels or fractions')
    ap.add_argument('--diff', action='store_true', help='with two images: add a tile showing the changed pixels')
    ap.add_argument('--background', default='#ececef')
    args = ap.parse_args()
    if args.labels and len(args.labels) != len(args.images):
        ap.error(f'{len(args.images)} images but {len(args.labels)} labels')
    if args.diff and len(args.images) != 2:
        ap.error('--diff compares exactly two images')

    originals = [flatten(Image.open(p), args.background) for p in args.images]
    labels = list(args.labels or [p.stem for p in args.images])
    if args.diff:
        tile, share = diff_tile(*originals)
        originals.append(tile)
        labels.append(f'changed: {share:.2%}')
        print(f'{share:.2%} of pixels changed')

    height = args.height or min(min(o.height for o in originals), 900)
    tiles = [o.resize((round(o.width * height / o.height), height), Image.LANCZOS) for o in originals]
    cols = args.cols or len(tiles)
    label_size = max(16, round(height / 28))

    if args.zoom:
        crops = [o.crop(crop_box(args.zoom, o.size)) for o in originals]
        cell_w = max(t.width for t in tiles)
        crops = [c.resize((cell_w, round(c.height * cell_w / c.width)), Image.LANCZOS) for c in crops]
        # Each image above its own crop, so the pairs stay together in any grid.
        tiles = [stack(t, c, args.background) for t, c in zip(tiles, crops)]

    out = sheet(tiles, labels, cols, args.background, label_size)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    out.save(args.out)
    print(f'{args.out}  ({len(originals)} images, {out.width}x{out.height})')


def stack(top, bottom, background):
    out = Image.new('RGB', (max(top.width, bottom.width), top.height + GAP // 2 + bottom.height), background)
    out.paste(top, ((out.width - top.width) // 2, 0))
    out.paste(bottom, ((out.width - bottom.width) // 2, top.height + GAP // 2))
    ImageDraw.Draw(out).rectangle([0, top.height + GAP // 2, out.width - 1, out.height - 1], outline='#999', width=2)
    return out


if __name__ == '__main__':
    main()
