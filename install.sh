#!/usr/bin/env bash
# Install brewcat on Linux (also works on macOS).
#   curl -fsSL https://raw.githubusercontent.com/1985epma/homebrew-brewcat/main/install.sh | bash
set -euo pipefail
REPO="https://github.com/1985epma/homebrew-brewcat.git"
DEST="${BREWCAT_HOME:-$HOME/.local/share/brewcat}"
BIN="$HOME/.local/bin"

command -v git >/dev/null || { echo "git is required"; exit 1; }

# Tk is required for the GUI.
if ! python3 -c "import tkinter" 2>/dev/null; then
  if command -v apt-get >/dev/null; then sudo apt-get install -y python3-tk
  elif command -v dnf >/dev/null; then sudo dnf install -y python3-tkinter
  elif command -v pacman >/dev/null; then sudo pacman -S --noconfirm tk
  elif command -v brew >/dev/null; then brew install python-tk
  else echo "Please install Python's Tk bindings (python3-tk) and re-run."; exit 1; fi
fi
command -v brew >/dev/null || echo "Note: Homebrew not found. Install it from https://brew.sh to install packages from the app."

# Install a released tag instead of the moving `main` branch. Pin one with: BREWCAT_REF=v0.1.2.3
REF="${BREWCAT_REF:-$(git ls-remote --tags --refs "$REPO" 'v*' | awk -F/ '{print $NF}' | sort -V | tail -1)}"
REF="${REF:-main}"
if [ -d "$DEST/.git" ]; then
  git -C "$DEST" fetch --depth 1 origin "$REF"
  git -C "$DEST" -c advice.detachedHead=false checkout -q FETCH_HEAD
else
  git -c advice.detachedHead=false clone --depth 1 --branch "$REF" "$REPO" "$DEST"
fi
echo "Installed brewcat $REF ($(git -C "$DEST" rev-parse --short HEAD))"

mkdir -p "$BIN"
cat > "$BIN/brewcat" <<LAUNCH
#!/usr/bin/env bash
exec python3 "$DEST/app.py" "\$@"
LAUNCH
chmod +x "$BIN/brewcat"

if [ "$(uname)" = "Linux" ]; then
  mkdir -p "$HOME/.local/share/applications"
  cat > "$HOME/.local/share/applications/brewcat.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=brewcat
Comment=Catalog of Homebrew packages, skills and MCP servers
Exec=$BIN/brewcat
Terminal=false
Categories=Development;Utility;
DESKTOP
fi

echo "Installed. Run: brewcat   (make sure $BIN is in your PATH)"
