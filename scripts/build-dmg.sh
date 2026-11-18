#!/bin/bash
# Build dist/brewcat-<version>.dmg containing the native brewcat.app (macOS only).
#
#   scripts/build-dmg.sh [VERSION]       # builds for this Mac's architecture
#   UNIVERSAL=1 scripts/build-dmg.sh     # arm64 + x86_64 in one binary (needs both Rust targets installed)
#
# VERSION defaults to the one in Cargo.toml.
set -euo pipefail
cd "$(dirname "$0")/.."
VERSION="${1:-$(sed -n 's/^version = "\(.*\)"$/\1/p' Cargo.toml | head -1)}"
[[ -n $VERSION ]] || { echo "build-dmg: cannot read the version from Cargo.toml" >&2; exit 1; }
APP="dist/brewcat.app"
OUT="${CARGO_TARGET_DIR:-target}"
rm -rf dist && mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"

if [[ ${UNIVERSAL:-0} == 1 ]]; then
  TARGETS=(aarch64-apple-darwin x86_64-apple-darwin)
  RUSTLIB="$(rustc --print sysroot)/lib/rustlib"
  for t in "${TARGETS[@]}"; do
    [[ -d $RUSTLIB/$t ]] || { echo "build-dmg: Rust target $t is not installed (rustup target add $t)" >&2; exit 1; }
  done
  for t in "${TARGETS[@]}"; do
    cargo build --release --locked --target "$t"
  done
  lipo -create -output "$APP/Contents/MacOS/brewcat" \
    "$OUT/${TARGETS[0]}/release/brewcat" "$OUT/${TARGETS[1]}/release/brewcat"
else
  cargo build --release --locked
  cp "$OUT/release/brewcat" "$APP/Contents/MacOS/brewcat"
fi
chmod 755 "$APP/Contents/MacOS/brewcat"
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
         brew tap 1985epma/brewcat && brew install --cask brewcat

brewcat needs Homebrew to install packages: https://brew.sh
On Apple Silicon, brewcat also offers to install Rosetta 2 for Intel-only apps.
TXT
hdiutil create -volname "brewcat" -srcfolder "$STAGE" -ov -format UDZO "dist/brewcat-${VERSION}.dmg" >/dev/null
rm -rf "$STAGE"
echo "Built dist/brewcat-${VERSION}.dmg"
