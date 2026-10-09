#!/bin/bash
# Builds "Emulaunch.app" into app/build/.
# Needs the Xcode Command Line Tools (xcode-select --install).
set -euo pipefail
cd "$(dirname "$0")"
APP="build/Emulaunch.app"

rm -rf build && mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources" build/tmp

echo "• drawing icon"
swiftc -O make_icon.swift -o build/tmp/make_icon -framework AppKit
build/tmp/make_icon build/tmp/AppIcon.iconset >/dev/null
iconutil -c icns build/tmp/AppIcon.iconset -o "$APP/Contents/Resources/AppIcon.icns"

echo "• compiling app"
swiftc -O main.swift -o "$APP/Contents/MacOS/Emulaunch" -framework Cocoa -framework WebKit

echo "• bundling launcher"
cp -R ../launcher "$APP/Contents/Resources/launcher"
find "$APP" -name "__pycache__" -prune -exec rm -rf {} +

cat > "$APP/Contents/Info.plist" <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>Emulaunch</string>
  <key>CFBundleDisplayName</key><string>Emulaunch</string>
  <key>CFBundleIdentifier</key><string>local.emulaunch</string>
  <key>CFBundleExecutable</key><string>Emulaunch</string>
  <key>CFBundleIconFile</key><string>AppIcon</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>CFBundleVersion</key><string>1</string>
  <key>LSMinimumSystemVersion</key><string>12.0</string>
  <key>NSHighResolutionCapable</key><true/>
  <key>NSAppTransportSecurity</key><dict><key>NSAllowsLocalNetworking</key><true/></dict>
</dict></plist>
EOF

codesign --force --deep -s - "$APP" >/dev/null 2>&1
rm -rf build/tmp
echo "✓ built $PWD/$APP"
