# Whip Cursor

**Will this make your AI better?** No. But you might feel like it does.

**Will it boost your efficiency?** Absolutely not.

**Is it fun, and eventually a little annoying?** Yes.

Your pointer grows a leather bullwhip. Click, and it cracks. Hold, and it loads. None of this makes a model smarter. It just sounds like you meant it.

Want your AI to actually work better? [Talk to Nebula 500](https://www.nebula500.com/). Or keep clicking harder and see if that helps.

## What you get

The same whip on every platform:

- Length 180–540, default 340
- Thickness 50%–250%, default 100%
- Handles: Straight, Tapered, Flared
- Colors: Ember, Mint, Lavender, Ice, Rose, Pearl, or a custom color
- Sounds: Classic bullwhip, Sharp snap, Dry crack, Swoosh + crack
- Volume default 45%
- Hold to load, or crack on each click. Either mouse button. A double-click is two cracks.
- The whip starts off every launch. Appearance is remembered. The on/off switch is not.
- Pause with Alt Shift W (Option Shift W on the Mac)

The rope math is the macOS simulation. Windows, Linux, and the web simulation are checked against a golden dump from that build. Do not retune one copy.

## macOS

macOS 13 or newer. The desktop app is the Swift menu-bar app.

```sh
cd Source
./build.sh
open "Whip Cursor.app"
```

Install notes are in `Source/Read Me First.txt`. Left-click the menu-bar whip to toggle it. Right-click for settings. The app does not watch your typing, use the network, or swallow clicks.

## Windows

Install Python 3.9 or newer from [python.org](https://www.python.org/downloads/windows/) so Tk is included. No extra packages.

```bat
py desktop\whip-cursor.py
```

A **WHIP OFF** button sits at the top of the screen. Click it to toggle. Right-click it for settings and quit. Closing the settings window leaves the button running. Alt Shift W pauses and brings the normal pointer back.

The whip window is click-through. The white dot on the handle is the real click point.

## Linux

Python 3.9 or newer, Tk, and an X11 session. XWayland can show the whip over X11 windows. A pure Wayland session can open settings and the preview, and will say so when the overlay is unavailable.

```sh
sudo apt install python3-tk libx11-6 libxext6 libxfixes3 libxinerama1
python3 desktop/whip-cursor.py
```

Sound uses `paplay`, `pw-play`, or `aplay`. The controls match Windows: the WHIP button, right-click menu, and Alt Shift W.

## Checks

```sh
python3 desktop/test_physics.py
node web/check-physics.js
```

Regenerate the macOS reference after a deliberate physics change:

```sh
xcrun swiftc -O -target arm64-apple-macosx13.0 Source/Sources/main.swift \
  -o /tmp/WhipCursorGolden \
  -framework AppKit -framework SwiftUI -framework AVFoundation \
  -framework CoreGraphics -framework Carbon
/tmp/WhipCursorGolden --physics-golden > desktop/physics-golden.txt
```

Update `desktop/whip_sim.py` and `web/whip.js` together, then re-run the checks. The numbers should agree within 1e-8.

## Layout

| Path | What it is |
| --- | --- |
| `Source/` | macOS app, build, and the recorded cracks |
| `desktop/` | Windows and Linux app, shared physics |
| `web/whip.js` | The same simulation and leather drawing for the web |
| `docs/physics.md` | What is locked, and why the coordinates are y-up |

## Sound credits

The whip recordings in `Source/Resources` are not covered by the MIT license. Joseph Sardin / BigSoundBank (LaSonothèque) dedicated them to the public domain under [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/). Details are in `Source/Resources/Audio-Credits.txt`.

## License

The code is [MIT](LICENSE). The recordings stay CC0.

## Privacy

No accounts, no analytics, no network calls from the desktop apps.
