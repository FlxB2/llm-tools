# flattenPdfFades

Makes gradient fades in a PDF render the same in every reader.

Design tools (Figma especially) export a "fade into the background" as a luminosity soft mask
filled with an axial shading, often nested in a second mask. macOS Preview, Poppler and others
drop or misdraw that, so the fade disappears or turns into a hard edge.

The script:

- renders each gradient-masked layer without its mask,
- evaluates the mask itself,
- composites the layers onto the plain background beneath them into one opaque image, and
- puts that image where the masked draws were.

Text and every other vector stay as they are. A mask that is just a solid rectangle becomes a
clip path, and a mask that covers everything is dropped. If the file does something the script
doesn't understand, it stops with a message and writes nothing.

## Usage

```sh
./flatten_pdf_fades.py in.pdf                 # writes "in (fixed).pdf"
./flatten_pdf_fades.py in.pdf -o out.pdf --dpi 300 --preview check.png
```

Needs [uv](https://docs.astral.sh/uv/), which installs pikepdf, numpy and Pillow from the inline
script header, and Poppler's `pdftocairo` on `PATH` (`brew install poppler`).

## Limits

- The faded layer must sit on a plain fill or the bare page. Anything drawn beneath it would be
  painted over by the flattened image, so the script refuses.
- Supported masks: one axis-aligned rectangle filled with a solid colour or an axial shading
  (function types 2, 3 and 4), optionally under nested masks of the same kind.
- The faded area becomes a raster at `--dpi` (300 by default, JPEG quality 92).

Re-run it after every export: a fresh export brings the masks back.
