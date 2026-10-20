#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# ///
"""Get an emulator or simulator ready for screenshots, and put it back afterwards.

Sets a clean status bar (9:41, full battery, full signal, no notifications), and optionally
light or dark mode and the language, on an Android emulator or an iOS simulator. Only
touches emulators and simulators: a physical Android phone is never picked unless named
with --device.

Usage: device_demo.py [--theme light|dark] [--locale de-DE [--app ID]] [--time 9:41]
                      [--platform android|ios] [--device SERIAL|UDID]
       device_demo.py --reset [--platform ...] [--device ...]

--locale changes the language of the whole device, or only of the app given with --app:
- Android: per app needs Android 13+; the whole device needs an emulator image without
  Google Play (adb root), and restarts the system UI.
- iOS: per app relaunches the app in that language; the whole device restarts the simulator.
Needs adb (Android) or Xcode's simctl (iOS) on PATH.
"""

import argparse
import json
import re
import subprocess
import sys


def run(*cmd, check=True):
    p = subprocess.run(cmd, capture_output=True, text=True)
    if check and p.returncode:
        sys.exit(f'failed: {" ".join(cmd)}\n{p.stderr.strip() or p.stdout.strip()}')
    return p.stdout.strip()


def has(tool):
    return subprocess.run(['which', tool], capture_output=True).returncode == 0


def android_devices():
    if not has('adb'):
        return []
    lines = run('adb', 'devices').splitlines()[1:]
    return [l.split()[0] for l in lines if l.endswith('\tdevice')]


def ios_devices():
    if not has('xcrun'):
        return []
    data = json.loads(run('xcrun', 'simctl', 'list', 'devices', 'booted', '-j', check=False) or '{}')
    return [d['udid'] for ds in data.get('devices', {}).values() for d in ds if d.get('state') == 'Booted']


def pick(platform, device):
    """The one device to work on, as (platform, id)."""
    if device:
        if platform:
            return platform, device
        if device in ios_devices():
            return 'ios', device
        return 'android', device  # named explicitly, so a physical phone is allowed
    found = []
    if platform in (None, 'android'):
        found += [('android', d) for d in android_devices() if d.startswith('emulator-')]
    if platform in (None, 'ios'):
        found += [('ios', d) for d in ios_devices()]
    if not found:
        sys.exit('no running emulator or booted simulator found')
    if len(found) > 1:
        sys.exit('several devices running; pick one with --device:\n' + '\n'.join(f'  {p}  {d}' for p, d in found))
    return found[0]


# --- Android -----------------------------------------------------------------------------

def adb(serial, *args, check=True):
    return run('adb', '-s', serial, *args, check=check)


def demo(serial, command, **extras):
    args = ['shell', 'am', 'broadcast', '-a', 'com.android.systemui.demo', '-e', 'command', command]
    for k, v in extras.items():
        args += ['-e', k, v]
    adb(serial, *args)


def android(serial, args):
    if args.reset:
        demo(serial, 'exit')
        print(f'{serial}: status bar back to normal')
        return
    adb(serial, 'shell', 'settings', 'put', 'global', 'sysui_demo_allowed', '1')
    demo(serial, 'enter')
    demo(serial, 'clock', hhmm=args.time.replace(':', '').zfill(4))
    demo(serial, 'battery', level='100', plugged='false')
    # Wifi only: newer system UIs show a mobile data type ("3G") whatever demo mode asks for.
    demo(serial, 'network', mobile='hide')
    demo(serial, 'network', wifi='show', level='4', fully='true')
    demo(serial, 'notifications', visible='false')  # older Android only; newer keeps real notification icons
    done = [f'status bar {args.time}']
    if args.theme:
        adb(serial, 'shell', 'cmd', 'uimode', 'night', 'yes' if args.theme == 'dark' else 'no')
        done.append(f'{args.theme} mode')
    if args.locale:
        if args.app:
            out = adb(serial, 'shell', 'cmd', 'locale', 'set-app-locales', args.app, '--locales', args.locale, check=False)
            if out or not adb(serial, 'shell', 'cmd', 'locale', 'get-app-locales', args.app, check=False).count(args.locale):
                sys.exit(f'{serial}: could not set the app locale (needs Android 13+ and an installed {args.app}): {out}')
            done.append(f'{args.app} in {args.locale}')
        else:
            if 'cannot run as root' in run('adb', '-s', serial, 'root', check=False):
                sys.exit(f'{serial}: changing the whole device language needs an emulator image without Google Play; '
                         'use --app to change one app instead')
            adb(serial, 'wait-for-device')
            adb(serial, 'shell', 'setprop', 'persist.sys.locale', args.locale)
            adb(serial, 'shell', 'setprop', 'ctl.restart', 'zygote')
            done.append(f'device in {args.locale} (system UI restarting; run again for the status bar once it is back)')
    print(f'{serial}: ' + ', '.join(done))


# --- iOS ---------------------------------------------------------------------------------

def simctl(*args, check=True):
    return run('xcrun', 'simctl', *args, check=check)


def ios_look(udid, args):
    simctl('status_bar', udid, 'override', '--time', args.time, '--dataNetwork', 'wifi', '--wifiMode', 'active',
           '--wifiBars', '3', '--cellularMode', 'active', '--cellularBars', '4', '--operatorName', '',
           '--batteryState', 'charged', '--batteryLevel', '100')
    if args.theme:
        simctl('ui', udid, 'appearance', args.theme)


def ios(udid, args):
    if args.reset:
        simctl('status_bar', udid, 'clear')
        print(f'{udid}: status bar back to normal')
        return
    ios_look(udid, args)
    done = [f'status bar {args.time}'] + ([f'{args.theme} mode'] if args.theme else [])
    if args.locale:
        lang = args.locale.split('-')[0]
        if args.app:
            simctl('terminate', udid, args.app, check=False)
            simctl('launch', udid, args.app, '-AppleLanguages', f'({lang})', '-AppleLocale', args.locale.replace('-', '_'))
            done.append(f'{args.app} relaunched in {args.locale}')
        else:
            simctl('spawn', udid, 'defaults', 'write', '-g', 'AppleLanguages', '-array', lang)
            simctl('spawn', udid, 'defaults', 'write', '-g', 'AppleLocale', '-string', args.locale.replace('-', '_'))
            simctl('shutdown', udid)
            simctl('boot', udid)
            simctl('bootstatus', udid)
            ios_look(udid, args)  # the restart drops the status bar override
            done.append(f'device in {args.locale} (simulator restarted)')
    print(f'{udid}: ' + ', '.join(done))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--platform', choices=['android', 'ios'])
    ap.add_argument('--device', help='adb serial or simulator UDID (default: the one running emulator or simulator)')
    ap.add_argument('--time', default='9:41', help='clock in the status bar (default 9:41)')
    ap.add_argument('--theme', choices=['light', 'dark'])
    ap.add_argument('--locale', help='language and region, e.g. de-DE')
    ap.add_argument('--app', help='Android package or iOS bundle ID: change the language of this app only')
    ap.add_argument('--reset', help='put the normal status bar back', action='store_true')
    args = ap.parse_args()
    if not re.fullmatch(r'\d{1,2}:\d{2}', args.time):
        ap.error('--time takes H:MM or HH:MM')
    if args.app and not args.locale:
        ap.error('--app goes with --locale')

    platform, device = pick(args.platform, args.device)
    (android if platform == 'android' else ios)(device, args)


if __name__ == '__main__':
    main()
