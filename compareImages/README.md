# compareImages

Puts images side by side with labels, to compare design variants, a before and after, or
screenshot test results, in one picture.

- Every image is scaled to the same height and labelled with its file name, or with `--labels`.
- `--zoom` adds an enlarged crop of the same region of each image underneath it, for details
  too small to judge at full size.
- `--diff`, with two images of the same size, adds a third tile with the changed pixels in red
  over a faded copy, and prints the share of pixels that changed.

## Usage

Needs [uv](https://docs.astral.sh/uv/), which installs Pillow on the first run.

```sh
./compare_images.py before.png after.png --diff                 # writes compare.png
./compare_images.py a.png b.png c.png --labels Blue Green Plain -o variants.png
./compare_images.py shots/*.png --cols 4 --height 600 -o sheet.png
./compare_images.py old.png new.png --zoom 0,0,1,0.1            # top tenth of each, enlarged
```

| Option | |
| --- | --- |
| `-o` | Output file (default `compare.png`). |
| `--labels` | One label per image. |
| `--cols` | Images per row (default: all in one row). |
| `--height` | Height every image is scaled to (default: the smallest, at most 900 px). |
| `--zoom x,y,w,h` | Region to enlarge, in pixels or as fractions of each image (all values ≤ 1). |
| `--diff` | Highlight what changed between two images. |
| `--background` | Sheet colour; transparent images are shown over it. |

## What it does not do

- `--diff` compares pixels exactly (with a small tolerance), so it can't line up images that
  moved or were resized; it refuses images of different sizes.
- It doesn't annotate, crop or edit the images themselves.
