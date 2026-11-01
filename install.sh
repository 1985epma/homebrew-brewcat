#!/usr/bin/env bash
# Install brewcat on Linux (also works on macOS).
#   curl -fsSL https://raw.githubusercontent.com/1985epma/homebrew-brewcat/main/install.sh | bash
set -euo pipefail
REPO="https://github.com/1985epma/homebrew-brewcat.git"
DEST="${BREWCAT_HOME:-$HOME/.local/share/brewcat}"
BIN="$HOME/.local/bin"

command -v git >/dev/null || { echo "git is required"; exit 1; }
command -v python3 >/dev/null || { echo "python3 is required"; exit 1; }
SUDO=sudo; [ "$(id -u)" = 0 ] && SUDO=""

# Tk is required for the GUI.
if ! python3 -c "import tkinter" 2>/dev/null; then
  if command -v apt-get >/dev/null; then $SUDO apt-get update && $SUDO apt-get install -y python3-tk
  elif command -v dnf >/dev/null; then $SUDO dnf install -y python3-tkinter
  elif command -v pacman >/dev/null; then $SUDO pacman -S --noconfirm tk
  elif command -v zypper >/dev/null; then $SUDO zypper --non-interactive install python3-tk
  elif command -v apk >/dev/null; then $SUDO apk add py3-tkinter
  elif command -v brew >/dev/null; then brew install python-tk
  else echo "Please install Python's Tk bindings (python3-tk) and re-run."; exit 1; fi
fi
command -v brew >/dev/null || echo "Note: Homebrew not found. Install it from https://brew.sh to install packages from the app."

# Install a released tag instead of the moving `main` branch. Pin one with: BREWCAT_REF=v0.1.2.3
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
Icon=$DEST/assets/brewcat.png
Terminal=false
Categories=Development;Utility;
DESKTOP
fi

echo "Installed. Run: brewcat   (make sure $BIN is in your PATH)"
