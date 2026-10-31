WHIP CURSOR 1.4.3 — SOURCE

The ready-to-run app and transfer instructions are on the GitHub Releases page:
https://github.com/nebula500/whip-cursor/releases

BUILD
Install Apple’s Command Line Tools, then run:
    ./build.sh

The script creates “Whip Cursor.app” with arm64 and x86_64 slices, targeting
macOS 13+. It uses a local ad-hoc signature; Apple notarization is not included.
Set WHIP_BUILD_ROOT or WHIP_BUILD_CACHE to put build artifacts elsewhere.

PACKAGE
    ./package.sh
or supply a destination:
    ./package.sh "/path/to/Whip Cursor.zip"

The package includes the app, Read Me First, and source. It replaces the
single destination ZIP. Temporary staging files are cleaned automatically.

CHECK
    "Whip Cursor.app/Contents/MacOS/WhipCursor" --self-test

Render checks:
    "Whip Cursor.app/Contents/MacOS/WhipCursor" --render-test --handle flared /tmp/handle.png
    "Whip Cursor.app/Contents/MacOS/WhipCursor" --render-test --loaded /tmp/loaded.png
    "Whip Cursor.app/Contents/MacOS/WhipCursor" --render-test --output /tmp/whip.png

Physics reference for the Windows, Linux, and web ports:
    "Whip Cursor.app/Contents/MacOS/WhipCursor" --physics-golden

The public project lives next to this folder: README.md and desktop/.
Windows and Linux run desktop/whip-cursor.py. The rope math is this file's
simulation. Do not retune one platform. See docs/physics.md.

IMPLEMENTATION
Sources/main.swift: AppKit + SwiftUI interface, rope physics, mouse state,
menu bar toggle, global pause hotkey, and paired cursor hide/show handling.
Resources/: four recorded sound options and Audio-Credits.txt.

Cursor replacement dynamically resolves CGSMainConnectionID (or
_CGSDefaultConnection) and CGSSetConnectionProperty and enables the private
SetsCursorInBackground property before calling CGDisplayHideCursor.
CGDisplayShowCursor is paired on every display that was successfully hidden.
Sudden termination is disabled while the pointer is hidden, and restore also
runs from applicationShouldTerminate. The connection property is restored on
pause, menu interaction, sleep, and exit.
No mouse events are intercepted or changed. The app has no network features,
analytics, microphone access, or screen recording. A Carbon hotkey handles
Option-Shift-W without monitoring typed keys.

Private macOS interfaces may change. Failure preserves the visible pointer.
Hiding reference counts are not repeatedly incremented by the render timer.
The visual overlay is shown before the system pointer is hidden.

References:
https://developer.apple.com/documentation/coregraphics/cgdisplayhidecursor(_:)
https://github.com/ggreer/CursorHide/blob/master/CursorHide/AppDelegate.m
https://github.com/Simone3/mac-hide-cursor
Audio licensing and recording sources: Resources/Audio-Credits.txt
