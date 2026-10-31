#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")"
OUTPUT="${1:-$PWD/Whip Cursor.zip}"
if [[ "${WHIP_SKIP_BUILD:-0}" != "1" ]]; then ./build.sh; fi
APP="$PWD/Whip Cursor.app"
"$APP/Contents/MacOS/WhipCursor" --self-test
codesign --verify --deep --strict "$APP"
ARCHS="$(xcrun lipo -archs "$APP/Contents/MacOS/WhipCursor")"
case "$ARCHS" in
    *arm64*x86_64*|*x86_64*arm64*) ;;
    *) echo 'Universal binary check failed.' >&2; exit 1 ;;
esac
STAGE="$(mktemp -d "${TMPDIR:-/tmp}/whip-package.XXXXXX")"
trap 'rm -rf "$STAGE"' EXIT
PACKAGE="$STAGE/Whip Cursor"
mkdir -p "$PACKAGE/Source" "$(dirname "$OUTPUT")"
ditto "$APP" "$PACKAGE/Whip Cursor.app"
cp 'Read Me First.txt' "$PACKAGE/Read Me First.txt"
for ITEM in Sources Resources Info.plist README.txt 'Read Me First.txt' build.sh package.sh; do
    ditto "$ITEM" "$PACKAGE/Source/$ITEM"
done
ditto -c -k --sequesterRsrc --keepParent "$PACKAGE" "$STAGE/Whip Cursor.zip"
unzip -tq "$STAGE/Whip Cursor.zip"
mv -f "$STAGE/Whip Cursor.zip" "$OUTPUT"
printf 'Ready to transfer: %s\n' "$OUTPUT"
