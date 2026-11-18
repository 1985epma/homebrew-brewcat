#!/usr/bin/env bash
# Install brewcat from source on Linux (also works on macOS): builds the latest released version with Rust.
#   curl -fsSL https://raw.githubusercontent.com/1985epma/homebrew-brewcat/main/install.sh | bash
# Needs git and a Rust toolchain (cargo). The first build takes a few minutes.
set -euo pipefail
REPO="${BREWCAT_REPO:-https://github.com/1985epma/homebrew-brewcat.git}"
DEST="${BREWCAT_HOME:-$HOME/.local/share/brewcat}"
BIN="$HOME/.local/bin"

command -v git >/dev/null || { echo "git is required"; exit 1; }
if ! command -v cargo >/dev/null; then
  echo "A Rust toolchain (cargo) is required to build brewcat. Get it with one of:"
  command -v brew >/dev/null && echo "  brew install rust"
  echo "  https://rustup.rs  (the official installer; review it before running)"
  exit 1
fi
command -v brew >/dev/null || echo "Note: Homebrew not found. Install it from https://brew.sh to install packages from the app."

# Install a released tag instead of the moving `main` branch. Pin one with: BREWCAT_REF=v0.2.0
if [ -z "${BREWCAT_REF:-}" ]; then
  TAGS=$(git ls-remote --tags --refs "$REPO" 'v*') || { echo "Cannot reach GitHub ($REPO). Check your connection and try again."; exit 1; }
  BREWCAT_REF=$(printf '%s\n' "$TAGS" | awk -F/ '{print $NF}' | sort -V | tail -1)
fi
REF="${BREWCAT_REF:-main}"
if [ -d "$DEST/.git" ]; then
  git -C "$DEST" fetch --depth 1 origin "$REF"
  git -C "$DEST" -c advice.detachedHead=false checkout -q FETCH_HEAD
else
  git -c advice.detachedHead=false clone --depth 1 --branch "$REF" "$REPO" "$DEST"
fi
echo "Fetched brewcat $REF ($(git -C "$DEST" rev-parse --short HEAD))"
if [ ! -f "$DEST/Cargo.toml" ]; then
  echo "$REF is older than brewcat 0.2.0, the first release written in Rust, so there is nothing to build."
  echo "Use BREWCAT_REF=v0.2.0 (or newer)."
  exit 1
fi

echo "Building brewcat (a few minutes the first time)…"
(cd "$DEST" && cargo build --release --locked)
mkdir -p "$BIN"
install -m 755 "$DEST/target/release/brewcat" "$BIN/brewcat"  # a copy, so a later `cargo clean` cannot break it

if [ "$(uname)" = "Linux" ]; then
  mkdir -p "$HOME/.local/share/applications"
  cat > "$HOME/.local/share/applications/brewcat.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=brewcat
Comment=Catalog of Homebrew packages, skills and MCP servers
Exec=$BIN/brewcat
Icon=$DEST/assets/brewcat.png
Terminal=false
Categories=Development;Utility;
DESKTOP
  echo "Note: the window needs a graphical session and OpenGL/EGL or Vulkan drivers (libEGL, libGL or libvulkan)."
  echo "      The command line works without them. Run 'brewcat doctor' to check."
fi

echo "Installed. Run: brewcat   (make sure $BIN is in your PATH)"
