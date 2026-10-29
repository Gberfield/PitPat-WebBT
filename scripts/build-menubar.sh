#!/bin/sh
# Builds the ad-hoc signed menu bar app into integration/macos/PitPatMenuBar/.build/PitPat.app
# and the PitPat Safety.app launcher into .build/PitPatSafety (the installer signs that bundle).
set -eu
cd "$(dirname "$0")/../integration/macos/PitPatMenuBar"
swift build -c release
bin=$(swift build -c release --show-bin-path)
app=.build/PitPat.app
rm -rf "$app"
mkdir -p "$app/Contents/MacOS"
cp Info.plist "$app/Contents/Info.plist"
cp "$bin/PitPatMenuBar" "$app/Contents/MacOS/PitPatMenuBar"
codesign --force --sign - "$app"
cp "$bin/PitPatSafety" .build/PitPatSafety
echo "$PWD/$app"
