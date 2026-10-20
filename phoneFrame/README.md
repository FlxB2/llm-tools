# phoneFrame

Puts a phone frame around iOS or Android screenshots, for landing pages, store listings, decks
and docs. The frame is drawn to fit the screenshot, so no device art is needed.

- **iOS:** an iPhone with a metal rim, side buttons and a Dynamic Island, a notch or neither,
  depending on the model the screenshot came from.
- **Android:** a slimmer phone with a punch-hole camera and buttons on the right.

The platform and cutout are guessed from the resolution: iPhone screenshots come in a few fixed
sizes, and anything else is treated as Android. Landscape screenshots get a landscape frame.

## Usage

Needs [uv](https://docs.astral.sh/uv/), which installs Pillow on the first run.

```sh
./phone_frame.py shot.png                          # writes shot-framed.png next to it
./phone_frame.py screens/*.png --out-dir framed    # several at once
./phone_frame.py shot.png -o hero.png --width 1000 --background '#ffffff'
./phone_frame.py shot.png --platform android --cutout none --color '#e3d9c6'
```

| Option | |
| --- | --- |
| `--platform auto\|ios\|android` | Which phone to draw. |
| `--cutout auto\|island\|notch\|hole\|none` | Camera cutout drawn over the top of the screen. |
| `--color` | Colour of the metal rim and buttons. |
| `--radius` | Screen corner radius as a fraction of the screen width (iOS 0.145, Android 0.085). |
| `--width` | Scale the result to this width in pixels. |
| `--background` | Fill the transparent surround; leave it out for a transparent PNG. |
| `--mockup frame.svg` | Use a real device frame instead (see below). |

### Your own device frame

`--mockup` takes an SVG exported from a design tool (Figma, for example) that has a device frame
with one screen in it: two rects filled with embedded PNGs, the screen first and the frame on top.
The screenshot is scaled into the screen's place, its corners rounded by `--radius`, and the frame
laid over it. The output has the frame picture's size.

## What it does not do

- It draws a generic phone, not a specific model. For an exact device, use `--mockup`.
- In landscape, the camera is always on the left edge.
- It does not add shadows, tilt or perspective, and it does not add a status bar the screenshot
  lacks.
- `--mockup` only reads that one SVG layout. A screenshot with a different aspect ratio from the
  mock-up's screen is stretched, with a warning.
