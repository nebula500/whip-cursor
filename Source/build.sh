#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
APP="$PWD/Whip Cursor.app"
BUILD="${WHIP_BUILD_ROOT:-$PWD/.build}"
CACHE="${WHIP_BUILD_CACHE:-$BUILD/module-cache}"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources" "$BUILD" "$CACHE"
for ARCH in arm64 x86_64; do
    xcrun swiftc -O -module-cache-path "$CACHE" -target "$ARCH-apple-macosx13.0" Sources/main.swift -o "$BUILD/WhipCursor-$ARCH" -framework AppKit -framework SwiftUI -framework AVFoundation -framework CoreGraphics -framework Carbon
done
xcrun lipo -create "$BUILD/WhipCursor-arm64" "$BUILD/WhipCursor-x86_64" -output "$APP/Contents/MacOS/WhipCursor"
cp Resources/crack-*.wav Resources/Audio-Credits.txt Resources/WhipCursor.icns "$APP/Contents/Resources/"
cp Info.plist "$APP/Contents/Info.plist"
xattr -cr "$APP" 2>/dev/null || true
xattr -d com.apple.FinderInfo "$APP" 2>/dev/null || true
codesign --force --sign - "$APP"
codesign --verify --deep --strict "$APP"
xcrun lipo -archs "$APP/Contents/MacOS/WhipCursor"
printf 'Built universal Mac app: %s\n' "$APP"
