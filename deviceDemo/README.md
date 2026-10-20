# deviceDemo

Gets an Android emulator or iOS simulator ready for screenshots, and puts it back afterwards:
a clean status bar (9:41, full battery, full wifi), and optionally light or dark mode and the
language of the device or of one app.

It covers the device settings that UI automation tools such as Maestro don't. Run it before
capturing screenshots, then frame them with [phoneFrame](../phoneFrame/).

## Usage

Needs `adb` (Android) or Xcode's `simctl` (iOS) on PATH, and [uv](https://docs.astral.sh/uv/).
With exactly one emulator or simulator running it picks that one; otherwise name it with
`--device` (an adb serial or simulator UDID) or narrow it with `--platform`.

```sh
./device_demo.py                                   # clean status bar
./device_demo.py --theme dark --time 10:08
./device_demo.py --locale de-DE                    # whole device in German
./device_demo.py --locale fr-FR --app com.example.app   # one app in French
./device_demo.py --reset                           # normal status bar again
```

| Option | |
| --- | --- |
| `--time H:MM` | Clock in the status bar (default 9:41). |
| `--theme light\|dark` | System appearance. |
| `--locale xx-YY` | Language and region of the whole device, or of `--app` only. |
| `--app ID` | Android package or iOS bundle ID whose language to change. |
| `--reset` | Put the normal status bar back. |
| `--platform android\|ios`, `--device ID` | Which device to use. |

How the language is changed:

| | Whole device | One app (`--app`) |
| --- | --- | --- |
| Android | Restarts the system UI. Needs an emulator image without Google Play (`adb root`). | Android 13+, no restart. |
| iOS | Restarts the simulator, then sets the status bar again. | Relaunches the app in that language. |

## What it does not do

- It never picks a physical Android phone by itself; name one with `--device` if you mean it.
- `--reset` only restores the status bar. Set the theme and language back with `--theme` and
  `--locale`.
- On newer Android versions, real notification icons stay on the left of the status bar, and
  mobile data is hidden because demo mode can't hide its type label ("3G") there.
- iOS may show the time with a leading zero (09:41) when the simulator uses a 24-hour region.
- It doesn't take screenshots or touch the app's UI. Use the automation tool you already drive
  the app with.
