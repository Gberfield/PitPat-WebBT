#!/bin/sh
# Build the app with Xcode's App Intents extraction; SPM still builds/tests the same sources.
# Outputs stay .build/PitPat.app (ad-hoc signed) and .build/PitPatSafety.
set -eu
cd "$(dirname "$0")/../integration/macos/PitPatMenuBar"
developer=$(xcode-select -p)
if [ ! -d "$developer/Platforms/MacOSX.platform" ] || ! xcrun --find appintentsmetadataprocessor >/dev/null 2>&1; then
    echo "PitPat app build requires full Xcode selected with xcode-select (not Command Line Tools)." >&2
    exit 1
fi
xcodebuild -project PitPat.xcodeproj -scheme PitPatMenuBar -configuration Release \
    -destination 'platform=macOS' -derivedDataPath "$PWD/.build/xcode" build
built=.build/xcode/Build/Products/Release/PitPat.app
metadata=Contents/Resources/Metadata.appintents
if [ ! -d "$built/$metadata" ] || [ -z "$(find "$built/$metadata" -type f -print)" ]; then
    echo "Xcode did not produce App Intents metadata: $built/$metadata" >&2
    exit 1
fi
app=.build/PitPat.app
rm -rf "$app"
cp -R "$built" "$app"
codesign --force --sign - "$app"
swift build -c release --product PitPatSafety
bin=$(swift build -c release --show-bin-path)
cp "$bin/PitPatSafety" .build/PitPatSafety
echo "$PWD/$app"
