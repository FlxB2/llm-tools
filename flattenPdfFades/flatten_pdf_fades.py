#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pikepdf>=9", "numpy", "pillow"]
# ///
"""Flatten soft-mask fades in a PDF so every reader draws them the same.

Design tools (Figma especially) export a "fade into the background" as a luminosity soft
mask whose group is filled with an axial shading driven by PostScript-calculator functions,
sometimes nested inside a second mask. Readers disagree on that combination: macOS Preview
and Poppler drop or misdraw the fade. This script replaces it with something every reader
handles:

- A masked layer that needs a real gradient is rendered without its mask (Poppler), the mask
  is evaluated here, and all such layers are composited onto the background they sit on into
  one opaque image that takes their place. Text and all other vectors stay untouched.
- A mask that is just a solid rectangle becomes a clip path; one that covers everything is
  dropped.

Anything it does not understand raises instead of guessing.

Usage: flatten_pdf_fades.py in.pdf [-o out.pdf] [--dpi 300] [--preview out.png]
Needs Poppler's pdftocairo on PATH.
"""

import argparse
import os
import subprocess
import sys
import tempfile

import numpy as np
import pikepdf
from pikepdf import Name, Operator
from PIL import Image

PAINT = {'f', 'F', 'f*', 'B', 'B*', 'b', 'b*', 'S', 's', 'sh', 'Do', 'Tj', 'TJ', "'", '"', 'INLINE IMAGE'}
STATE = {'cs', 'CS', 'sc', 'scn', 'SC', 'SCN', 'g', 'G', 'rg', 'RG', 'k', 'K', 'cm', 'w', 'J', 'j', 'M', 'd', 'ri', 'i'}
EPS = 0.5  # pt; tolerance for "covers the whole box"


class Unsupported(Exception):
    pass


# --- matrices: row vectors, p' = [x y 1] @ M, so "A then B" is A @ B ------------------------

def mat(a):
    a = [float(v) for v in a]
    return np.array([[a[0], a[1], 0], [a[2], a[3], 0], [a[4], a[5], 1]])


ID = np.eye(3)


def apply(m, pts):
    pts = np.asarray(pts, float)
    return (np.c_[pts, np.ones(len(pts))] @ m)[:, :2]


# --- PDF functions --------------------------------------------------------------------------

BIN = {
    'add': lambda a, b: a + b, 'sub': lambda a, b: a - b, 'mul': lambda a, b: a * b,
    'div': lambda a, b: a / b, 'exp': lambda a, b: a ** b, 'max': max, 'min': min,
    'gt': lambda a, b: a > b, 'lt': lambda a, b: a < b, 'ge': lambda a, b: a >= b,
    'le': lambda a, b: a <= b, 'eq': lambda a, b: a == b, 'ne': lambda a, b: a != b,
    'and': lambda a, b: a and b, 'or': lambda a, b: a or b,
}
UN = {
    'neg': lambda a: -a, 'abs': abs, 'not': lambda a: not a, 'cvr': float, 'cvi': lambda a: float(int(a)),
    'floor': np.floor, 'ceiling': np.ceil, 'round': lambda a: float(np.floor(a + 0.5)),
    'truncate': np.trunc, 'sqrt': np.sqrt,
}


def parse_ps(src):
    toks = src.replace('{', ' { ').replace('}', ' } ').split()

    def block(i):
        out = []
        while i < len(toks):
            if toks[i] == '{':
                sub, i = block(i + 1)
                out.append(sub)
            elif toks[i] == '}':
                return out, i + 1
            else:
                out.append(toks[i])
                i += 1
        return out, i

    prog, _ = block(0)
    if len(prog) != 1 or not isinstance(prog[0], list):
        raise Unsupported('malformed calculator function')
    return prog[0]


def run_ps(prog, st):
    for tk in prog:
        if isinstance(tk, list):
            st.append(tk)
        elif tk == 'if':
            p, c = st.pop(), st.pop()
            if c:
                run_ps(p, st)
        elif tk == 'ifelse':
            p2, p1, c = st.pop(), st.pop(), st.pop()
            run_ps(p1 if c else p2, st)
        elif tk in BIN:
            b, a = st.pop(), st.pop()
            st.append(BIN[tk](a, b))
        elif tk in UN:
            st.append(UN[tk](st.pop()))
        elif tk == 'exch':
            st[-1], st[-2] = st[-2], st[-1]
        elif tk == 'pop':
            st.pop()
        elif tk == 'dup':
            st.append(st[-1])
        elif tk == 'copy':
            n = int(st.pop())
            st.extend(st[len(st) - n:] if n else [])
        elif tk == 'index':
            n = int(st.pop())
            st.append(st[-1 - n])
        elif tk == 'roll':
            j, n = int(st.pop()), int(st.pop())
            if n:
                seg = st[-n:]
                j %= n
                st[-n:] = seg[-j:] + seg[:-j] if j else seg
        elif tk in ('true', 'false'):
            st.append(tk == 'true')
        else:
            try:
                st.append(float(tk))
            except ValueError:
                raise Unsupported(f'calculator operator {tk!r}')
    return st


def eval_fn(fn, t):
    if isinstance(fn, pikepdf.Array):
        return tuple(v for f in fn for v in eval_fn(f, t))
    ft = int(fn.FunctionType)
    if ft == 2:
        c0 = [float(v) for v in fn.get('/C0', [0])]
        c1 = [float(v) for v in fn.get('/C1', [1])]
        n = float(fn.N)
        return tuple(a + t ** n * (b - a) for a, b in zip(c0, c1))
    if ft == 3:
        dom = [float(v) for v in fn.Domain]
        bounds = [float(v) for v in fn.Bounds]
        enc = [float(v) for v in fn.Encode]
        edges = [dom[0], *bounds, dom[1]]
        k = next((i for i, b in enumerate(bounds) if t < b), len(bounds))
        lo, hi, e0, e1 = edges[k], edges[k + 1], enc[2 * k], enc[2 * k + 1]
        return eval_fn(fn.Functions[k], e0 if hi == lo else e0 + (t - lo) * (e1 - e0) / (hi - lo))
    if ft == 4:
        out = run_ps(parse_ps(fn.read_bytes().decode('latin1')), [t])
        rng = [float(v) for v in fn.Range]
        return tuple(min(max(float(v), rng[2 * i]), rng[2 * i + 1]) for i, v in enumerate(out))
    raise Unsupported(f'function type {ft}')


def luminosity(color):
    if len(color) == 1:
        return color[0]
    if len(color) == 3:
        r, g, b = color
        return 0.3 * r + 0.59 * g + 0.11 * b  # the PDF spec's non-separable luminosity
    raise Unsupported(f'{len(color)}-component colour in a mask')


# --- soft masks -----------------------------------------------------------------------------

def parse_mask(gs, to_target):
    """Read a soft mask whose group paints one rectangle with a solid colour or an axial
    shading, optionally under a nested mask. `to_target` maps the user space at the `gs`
    into the space the result is expressed in."""
    sm = gs.SMask
    if '/TR' in sm and sm.TR != Name.Identity:
        raise Unsupported('mask transfer function')
    if '/BC' in sm and any(float(v) for v in sm.BC):
        raise Unsupported('non-black mask backdrop')
    g = sm.G
    gspace = mat(g.get('/Matrix', [1, 0, 0, 1, 0, 0])) @ to_target
    spec = {'kind': str(sm.S), 'inner': None, 'fill': None, 'pts': None}
    cm, stack, path = ID, [], []
    for ins in pikepdf.parse_content_stream(g):
        op, args = str(ins.operator), list(ins.operands)
        if op == 'q':
            stack.append(cm)
        elif op == 'Q':
            cm = stack.pop()
        elif op == 'cm':
            cm = mat(args) @ cm
        elif op == 'gs':
            inner = g.Resources.ExtGState[args[0]]
            if set(inner.keys()) - {'/Type', '/SMask'}:
                raise Unsupported('mask group sets more than a nested mask')
            spec['inner'] = parse_mask(inner, cm @ gspace)
        elif op in ('m', 'l'):
            path.append(apply(cm @ gspace, [args])[0])
        elif op == 're':
            x, y, w, h = (float(v) for v in args)
            path += list(apply(cm @ gspace, [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]))
        elif op in ('scn', 'sc', 'g', 'rg'):
            if args and isinstance(args[-1], Name):
                pat = g.Resources.Pattern[args[-1]]
                if int(pat.PatternType) != 2 or int(pat.Shading.ShadingType) != 2:
                    raise Unsupported('mask filled with something other than an axial shading')
                spec['fill'] = ('axial', pat.Shading, mat(pat.get('/Matrix', [1, 0, 0, 1, 0, 0])) @ gspace)
            else:
                spec['fill'] = ('solid', tuple(float(v) for v in args))
        elif op in ('f', 'f*'):
            if spec['pts'] is not None:
                raise Unsupported('mask group paints more than one shape')
            spec['pts'] = np.array(path)
        elif op in ('h', 'n', 'cs', 'CS', 'BMC', 'BDC', 'EMC'):
            pass
        else:
            raise Unsupported(f'operator {op} in a mask group')
    pts = spec['pts']
    if pts is None or spec['fill'] is None:
        raise Unsupported('mask group paints nothing')
    lo, hi = pts.min(0), pts.max(0)
    on_edge = (np.isclose(pts, lo, atol=0.01) | np.isclose(pts, hi, atol=0.01)).all()
    if not on_edge:
        raise Unsupported('mask shape is not an axis-aligned rectangle')
    spec['rect'] = (lo, hi)
    return spec


def solid_value(spec):
    if spec['fill'][0] != 'solid' or spec['inner'] is not None:
        return None
    return luminosity(spec['fill'][1]) if spec['kind'] == '/Luminosity' else 1.0


def eval_mask(spec, X, Y):
    """Mask alpha at page points X, Y (spec must be in page space)."""
    if spec['fill'][0] == 'solid':
        v = np.full(X.shape, solid_value({**spec, 'inner': None}))
    else:
        _, sh, to_page = spec['fill']
        x0, y0, x1, y1 = (float(c) for c in sh.Coords)
        d0, d1 = (float(c) for c in sh.get('/Domain', [0, 1]))
        ext = [bool(e) for e in sh.get('/Extend', [False, False])]
        inv = np.linalg.inv(to_page)
        u = X * inv[0, 0] + Y * inv[1, 0] + inv[2, 0]
        w = X * inv[0, 1] + Y * inv[1, 1] + inv[2, 1]
        s = ((u - x0) * (x1 - x0) + (w - y0) * (y1 - y0)) / ((x1 - x0) ** 2 + (y1 - y0) ** 2)
        painted = ((s >= 0) | ext[0]) & ((s <= 1) | ext[1])
        lut_t = np.linspace(0, 1, 1025)
        lut = np.array([
            luminosity(eval_fn(sh.Function, d0 + t * (d1 - d0))) if spec['kind'] == '/Luminosity' else 1.0
            for t in lut_t])
        v = np.where(painted, np.interp(np.clip(s, 0, 1), lut_t, lut), 0)
    if spec['inner'] is not None:
        v = v * eval_mask(spec['inner'], X, Y)  # the fill's alpha scales its luminosity over black
    (lx, ly), (hx, hy) = spec['rect']
    return np.where((X >= lx) & (X <= hx) & (Y >= ly) & (Y <= hy), v, 0.0)


# --- content streams ------------------------------------------------------------------------

def walk(ops):
    """Yield (index, op, args, depth, ctm) with ctm relative to the container's space."""
    stack, ctm = [], ID
    for i, ins in enumerate(ops):
        op = str(ins.operator)
        args = list(ins.operands) if op != 'INLINE IMAGE' else []
        if op == 'q':
            yield i, op, args, len(stack), ctm
            stack.append(ctm)
            continue
        if op == 'Q':
            ctm = stack.pop()
            yield i, op, args, len(stack), ctm
            continue
        if op == 'cm':
            ctm = mat(args) @ ctm
        yield i, op, args, len(stack), ctm


def instr(op, *args):
    return pikepdf.ContentStreamInstruction([float(a) if isinstance(a, np.floating) else a for a in args], Operator(op))


def ops_of(obj):
    return list(pikepdf.parse_content_stream(obj))


def write_ops(pdf, target, ops):
    data = pikepdf.unparse_content_stream(ops)
    if isinstance(target, pikepdf.Page):
        target.Contents = pdf.make_stream(data)
    else:
        target.write(data)


def is_smask_gs(res, args):
    gs = res.ExtGState[args[0]]
    return '/SMask' in gs and gs.SMask != Name('/None')


# --- the fix --------------------------------------------------------------------------------

class Fixer:
    def __init__(self, src, dpi, log):
        self.src, self.dpi, self.log = src, dpi, log
        self.pdf = pikepdf.open(src)
        self.tmp = tempfile.mkdtemp(prefix='flatten-fades-')
        self.done = set()

    def run(self):
        for n, page in enumerate(self.pdf.pages):
            if int(page.get('/Rotate', 0)) % 360:
                raise Unsupported('rotated page')
            self.container(n, page, [], ID, page.Resources, [float(v) for v in page.cropbox])
        self.pdf.remove_unreferenced_resources()
        return self.pdf

    def container(self, n, obj, path, to_page, res, bbox):
        """Fix one content stream: the page (path []) or a form drawn by it (path [names])."""
        if not isinstance(obj, pikepdf.Page):
            if obj.objgen in self.done:
                return
            self.done.add(obj.objgen)
        ops = ops_of(obj)
        steps = list(walk(ops))
        repl, flatten, groups, open_q, children = {}, [], {}, None, []
        for i, op, args, depth, ctm in steps:
            if op == 'q' and depth == 0:
                open_q = i
            elif op == 'Q' and depth == 0:
                groups[open_q] = i
            elif op == 'gs' and is_smask_gs(res, args):
                gs = res.ExtGState[args[0]]
                if set(gs.keys()) - {'/Type', '/SMask'}:
                    raise Unsupported(f'{args[0]} sets more than a mask')
                spec = parse_mask(gs, ID)
                value = solid_value(spec)
                if value is not None and value >= 0.999:
                    (lx, ly), (hx, hy) = spec['rect']
                    corners = apply(ctm, [(lx, ly), (hx, ly), (hx, hy), (lx, hy)])
                    clo, chi = corners.min(0), corners.max(0)
                    if clo[0] <= bbox[0] + EPS and clo[1] <= bbox[1] + EPS and chi[0] >= bbox[2] - EPS and chi[1] >= bbox[3] - EPS:
                        repl[i] = []
                        self.log(f'page {n + 1} {"/".join(path) or "content"}: dropped {args[0]} (covers everything)')
                    else:
                        repl[i] = [instr('re', lx, ly, hx - lx, hy - ly), instr('W'), instr('n')]
                        self.log(f'page {n + 1} {"/".join(path) or "content"}: {args[0]} -> clip rectangle')
                else:
                    flatten.append((i, depth, ctm))
            elif op == 'Do':
                x = res.XObject[args[0]]
                if x.Subtype == Name.Form:
                    sub = mat(x.get('/Matrix', [1, 0, 0, 1, 0, 0])) @ ctm @ to_page
                    fb = [float(v) for v in x.BBox]
                    children.append((x, path + [str(args[0])[1:]], sub, x.get('/Resources', res), fb))

        if flatten:
            if len(path) > 1:
                raise Unsupported('gradient mask nested more than one form deep')
            repl.update(self.flatten(n, obj, path, to_page, res, bbox, ops, steps, flatten, groups))

        write_ops(self.pdf, obj, [new for i, ins in enumerate(ops) for new in repl.get(i, [ins])])
        # Children after the parent is written: rendering a child's layers re-reads the source,
        # and the parent's own fix doesn't depend on them.
        for x, child, sub, cres, fb in children:
            self.container(n, x, child, sub, cres, fb)

    def flatten(self, n, obj, path, to_page, res, bbox, ops, steps, flatten, groups):
        # Each gradient-masked draw must be its own top-level `q [cm] gs [cm] Do Q` group,
        # and those groups must follow each other.
        spans = []
        for i, depth, _ in flatten:
            start = max(s for s in groups if s < i)
            end = groups[start]
            inner = [str(ops[k].operator) for k in range(start + 1, end)]
            if sorted(set(inner) - {'cm'}) != ['Do', 'gs'] or inner.count('Do') != 1 or inner.count('gs') != 1:
                raise Unsupported('gradient mask is not on a plain `q gs Do Q` group')
            spans.append((start, end))
        spans.sort()
        for (_, e), (s, _) in zip(spans, spans[1:]):
            if s != e + 1:
                raise Unsupported('gradient-masked groups are not consecutive')
        first, last = spans[0][0], spans[-1][1]

        # Whatever sits beneath must be a plain fill of the whole box: that becomes the backdrop.
        backdrop, colour = np.ones(3), (1.0, 1.0, 1.0)
        for i, op, args, depth, ctm in steps:
            if i >= first:
                break
            if op in ('sc', 'scn', 'g', 'rg') and args and not isinstance(args[-1], Name):
                colour = tuple(float(a) for a in args)
            if op in ('f', 'F', 'f*'):
                if len(colour) not in (1, 3):
                    raise Unsupported('backdrop fill colour')
                backdrop = np.array(colour * 3 if len(colour) == 1 else colour)
            elif op in PAINT:
                raise Unsupported(f'something is drawn beneath the fade ({op})')
        if path:
            for i, op, args, depth, ctm in walk(ops_of(self.pdf.pages[n])):
                if op == 'Do' and str(args[0])[1:] == path[0]:
                    break
                if op in PAINT:
                    raise Unsupported(f'the page draws beneath the faded form ({op})')

        prefix = [ops[i] for i, op, _, depth, _ in steps if i < first and depth == 0 and op in STATE]
        layers = []
        for s, e in spans:
            body = [ops[k] for k in range(s, e + 1) if str(ops[k].operator) != 'gs']
            gs_i, gs_ctm = next((i, ctm) for i, op, _, _, ctm in steps if s < i < e and op == 'gs')
            spec = parse_mask(res.ExtGState[ops[gs_i].operands[0]], gs_ctm @ to_page)
            layers.append((self.render(n, path, prefix + body), spec))

        cb = [float(v) for v in self.pdf.pages[n].cropbox]
        H, W = layers[0][0].shape[:2]
        sx, sy = (cb[2] - cb[0]) / W, (cb[3] - cb[1]) / H
        X, Y = np.meshgrid(cb[0] + (np.arange(W) + 0.5) * sx, cb[3] - (np.arange(H) + 0.5) * sy)
        out = np.broadcast_to(backdrop * 255.0, (H, W, 3)).copy()
        reach = np.zeros((H, W), bool)
        for rgba, spec in layers:
            a = rgba[..., 3:4] / 255.0 * eval_mask(spec, X, Y)[..., None]
            out = out * (1 - a) + rgba[..., :3] * a
            reach |= a[..., 0] > 1 / 512
        rows, cols = np.where(reach.any(1))[0], np.where(reach.any(0))[0]
        if not len(rows):
            raise Unsupported('the masked layers draw nothing')
        r0, r1, c0, c1 = int(rows[0]), int(rows[-1]) + 1, int(cols[0]), int(cols[-1]) + 1
        crop = np.clip(np.round(out[r0:r1, c0:c1]), 0, 255).astype(np.uint8)
        jpg = os.path.join(self.tmp, f'flat-{n}-{len(path)}.jpg')
        Image.fromarray(crop).save(jpg, quality=92, subsampling=0)

        img = pikepdf.Stream(self.pdf, open(jpg, 'rb').read())
        img.Type, img.Subtype, img.Filter = Name.XObject, Name.Image, Name.DCTDecode
        img.Width, img.Height, img.BitsPerComponent, img.ColorSpace = c1 - c0, r1 - r0, 8, Name.DeviceRGB
        name = next(f'/Flat{k}' for k in range(1000) if f'/Flat{k}' not in res.XObject)
        res.XObject[name] = img

        x0, x1 = cb[0] + c0 * sx, cb[0] + c1 * sx
        y0, y1 = cb[3] - r1 * sy, cb[3] - r0 * sy
        group_ctm = next(ctm for i, _, _, _, ctm in steps if i == first)
        cm = mat([x1 - x0, 0, 0, y1 - y0, x0, y0]) @ np.linalg.inv(group_ctm @ to_page)
        self.log(f'page {n + 1} {"/".join(path) or "content"}: flattened {len(layers)} faded layer(s) '
                 f'into a {c1 - c0}x{r1 - r0} image at y {y0:.0f}-{y1:.0f} pt')
        repl = {k: [] for k in range(first + 1, last + 1)}
        repl[first] = [instr('q'), instr('cm', *[float(v) for v in cm[:, :2].ravel()]),
                       instr('Do', Name(name)), instr('Q')]
        return repl

    def render(self, n, path, body):
        """Render `body` alone, in place of the container's content, as RGBA."""
        pdf = pikepdf.open(self.src)
        page = pdf.pages[n]
        if not path:
            write_ops(pdf, page, body)
        else:
            write_ops(pdf, page.Resources.XObject['/' + path[0]], body)
            keep, depth = [], 0
            for i, op, args, d, _ in walk(page_ops := ops_of(page)):
                if op in ('BMC', 'BDC', 'EMC') or (op == 'gs' and is_smask_gs(page.Resources, args)):
                    continue
                keep.append(page_ops[i])
                depth = d + 1 if op == 'q' else d
                if op == 'Do' and str(args[0])[1:] == path[0]:
                    break
            write_ops(pdf, page, keep + [instr('Q')] * depth)
        tmp_pdf = os.path.join(self.tmp, 'layer.pdf')
        pdf.save(tmp_pdf)
        out = os.path.join(self.tmp, 'layer')
        subprocess.run(['pdftocairo', '-png', '-transp', '-r', str(self.dpi), '-f', str(n + 1), '-l', str(n + 1),
                        '-singlefile', tmp_pdf, out], check=True, capture_output=True)
        return np.asarray(Image.open(out + '.png').convert('RGBA'), dtype=np.float64)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('pdf')
    ap.add_argument('-o', '--out', help='default: "<name> (fixed).pdf" next to the input')
    ap.add_argument('--dpi', type=int, default=300)
    ap.add_argument('--preview', help='also render the result to this PNG')
    a = ap.parse_args()
    out = a.out or os.path.splitext(a.pdf)[0] + ' (fixed).pdf'

    pdf = Fixer(a.pdf, a.dpi, print).run()
    pdf.save(out, compress_streams=True, object_stream_mode=pikepdf.ObjectStreamMode.generate)

    left = sum(1 for o in pikepdf.open(out).objects
               if isinstance(o, pikepdf.Dictionary) and o.get('/Type') == Name.ExtGState and '/SMask' in o)
    print(f'wrote {out} ({os.path.getsize(a.pdf) // 1024} KB -> {os.path.getsize(out) // 1024} KB), '
          f'{left} soft-mask graphics state(s) left')
    if a.preview:
        subprocess.run(['pdftocairo', '-png', '-r', '100', '-singlefile', out, os.path.splitext(a.preview)[0]], check=True)


if __name__ == '__main__':
    try:
        main()
    except Unsupported as e:
        sys.exit(f'not flattened, nothing written: {e}')
