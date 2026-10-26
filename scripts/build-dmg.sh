#!/bin/bash
# Build dist/brewcat-<version>.dmg containing a launcher-style brewcat.app (macOS only).
set -euo pipefail
cd "$(dirname "$0")/.."
VERSION="${1:-0.1.2.4}"
APP="dist/brewcat.app"
rm -rf dist && mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

cp app.py catalog_data.py extras_tab.py logo.py help_text.py "$APP/Contents/Resources/"
cp assets/brewcat.icns "$APP/Contents/Resources/brewcat.icns"

cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>CFBundleName</key><string>brewcat</string>
  <key>CFBundleDisplayName</key><string>brewcat</string>
  <key>CFBundleIdentifier</key><string>com.github.1985epma.brewcat</string>
  <key>CFBundleVersion</key><string>${VERSION}</string>
  <key>CFBundleShortVersionString</key><string>${VERSION}</string>
  <key>CFBundleExecutable</key><string>brewcat</string>
  <key>CFBundleIconFile</key><string>brewcat</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>LSMinimumSystemVersion</key><string>11.0</string>
  <key>NSHighResolutionCapable</key><true/>
</dict></plist>
PLIST

cat > "$APP/Contents/MacOS/brewcat" <<'LAUNCH'
#!/bin/bash
# Finder-launched apps have a minimal PATH, so look for Homebrew's Python explicitly.
DIR="$(cd "$(dirname "$0")/../Resources" && pwd)"
for PY in /opt/homebrew/bin/python3 /usr/local/bin/python3; do
  if [ -x "$PY" ] && "$PY" -c "import tkinter" 2>/dev/null; then
    export TK_SILENCE_DEPRECATION=1
    exec "$PY" "$DIR/app.py"
  fi
done
osascript -e 'display dialog "brewcat needs Homebrew and python-tk.\n\nInstall them with:\n  brew install python-tk\n\nThen open the app again." buttons {"OK"} default button "OK" with icon caution with title "brewcat"'
LAUNCH
chmod +x "$APP/Contents/MacOS/brewcat"

# Ad-hoc sign (no Apple Developer ID): satisfies Apple Silicon's signature requirement. Gatekeeper will
# still warn for downloaded copies because the app is not notarized, so the DMG ships instructions.
codesign --force --deep --sign - "$APP" >/dev/null 2>&1 || echo "warning: ad-hoc codesign failed"

STAGE="dist/dmg"
mkdir -p "$STAGE" && cp -R "$APP" "$STAGE/" && ln -s /Applications "$STAGE/Applications"
cat > "$STAGE/READ ME FIRST.txt" <<'TXT'
brewcat is not notarized by Apple, so macOS may say it "could not verify brewcat is free of malware".
It is open source: https://github.com/1985epma/homebrew-brewcat

To open it:
  1. Drag brewcat to Applications.
  2. Open Terminal and run:
         xattr -dr com.apple.quarantine /Applications/brewcat.app
  3. Open brewcat normally.
  (Or: System Settings > Privacy & Security > scroll down > "Open Anyway".)

No warning at all if you install with Homebrew instead:
         brew tap 1985epma/brewcat && brew install brewcat && brewcat

brewcat needs python-tk:  brew install python-tk
On Apple Silicon, brewcat also offers to install Rosetta 2 for Intel-only apps.
TXT
hdiutil create -volname "brewcat" -srcfolder "$STAGE" -ov -format UDZO "dist/brewcat-${VERSION}.dmg" >/dev/null
rm -rf "$STAGE"
echo "Built dist/brewcat-${VERSION}.dmg"
