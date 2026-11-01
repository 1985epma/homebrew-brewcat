"""macOS launcher bundle: gives brewcat its own name and icon in Dock, menu bar and Launchpad.

No tkinter import here so it can run in headless/CLI contexts."""
from __future__ import annotations

import os
import re
import shutil
import sys
from typing import Optional

from help_text import VERSION


# The copied Python stub links to a versioned Homebrew path, so after `brew upgrade python` + `brew cleanup` it can
# no longer load. Check that before using it; otherwise start through the current Homebrew Python, whose
# ensure_branded_launcher() rebuilds this bundle (BREWCAT_BRANDED must not be set for that).
LAUNCHER_SCRIPT = """#!/bin/bash
export TK_SILENCE_DEPRECATION=1
@HIDDEN@HERE="$(cd "$(dirname "$0")" && pwd)"
if "$HERE/brewcat-python" -c "import tkinter" >/dev/null 2>&1; then
  export BREWCAT_BRANDED=1
  exec "$HERE/brewcat-python" "@SCRIPT@" "$@"
fi
for PY in /opt/homebrew/bin/python3 /usr/local/bin/python3; do
  [ -x "$PY" ] && exec "$PY" "@SCRIPT@" "$@"
done
/usr/bin/osascript -e 'display dialog "brewcat needs Homebrew and python-tk.\\n\\nInstall them with:\\n  brew install python-tk" buttons {"OK"} default button "OK" with icon caution with title "brewcat"'
"""


def bundle_state() -> Optional[str]:
    """None when ~/Applications/brewcat.app is healthy, else why it is not (used by `brewcat doctor`)."""
    base = os.path.expanduser("~/Applications/brewcat.app")
    try:
        with open(os.path.join(base, "Contents/.brewcat-build")) as fh:
            _version, stub, _script = fh.read().split("|", 2)
    except (OSError, ValueError):
        return "build marker missing"
    if not os.path.exists(stub):
        return "it was built from a Python that has since been removed"
    return None


def build_app_bundle() -> Optional[str]:
    """Create ~/Applications/brewcat.app (macOS) so brewcat shows up in Launchpad, Spotlight and Finder.
    The bundle holds a copy of Python's launcher stub, so macOS shows "brewcat" and the cat icon in the
    menu bar and Dock instead of "Python". Returns the path of the stub inside the bundle."""
    here = os.path.dirname(os.path.abspath(__file__))
    # Use brew's stable "opt" path so the app keeps working after `brew upgrade`.
    stable = re.sub(r"/Cellar/brewcat/[^/]+/libexec$", "/opt/brewcat/libexec", here)
    script = os.path.join(stable, "app.py")
    stub = os.path.join(sys.base_prefix, "Resources/Python.app/Contents/MacOS/Python")
    if not os.path.exists(stub) or not os.path.exists(script):
        return None
    # Normally a visible app in ~/Applications. When brewcat already runs from a /Applications copy (cask or
    # .dmg), keep the helper bundle hidden so Launchpad doesn't show two brewcat apps.
    base = os.path.expanduser("~/Library/Application Support/brewcat/brewcat.app"
                              if os.environ.get("BREWCAT_HIDDEN_APP") else "~/Applications/brewcat.app")
    macos = os.path.join(base, "Contents/MacOS")
    py_exe, launcher = os.path.join(macos, "brewcat-python"), os.path.join(macos, "brewcat")
    marker = os.path.join(base, "Contents/.brewcat-build")
    want = f"{VERSION}|{os.path.realpath(stub)}|{script}"
    try:
        with open(marker) as fh:
            built = fh.read()
    except OSError:
        built = ""
    if not (os.path.exists(py_exe) and os.path.exists(launcher) and built == want):
        shutil.rmtree(base, ignore_errors=True)
        os.makedirs(macos)
        os.makedirs(os.path.join(base, "Contents/Resources"))
        shutil.copy2(stub, py_exe)
        for icns in (os.path.join(here, "assets/brewcat.icns"), os.path.join(here, "brewcat.icns")):
            if os.path.exists(icns):
                shutil.copy2(icns, os.path.join(base, "Contents/Resources/brewcat.icns"))
                break
        with open(launcher, "w") as fh:  # what Finder/Launchpad run on double-click
            hidden = "export BREWCAT_HIDDEN_APP=1\n" if os.environ.get("BREWCAT_HIDDEN_APP") else ""
            fh.write(LAUNCHER_SCRIPT.replace("@HIDDEN@", hidden).replace("@SCRIPT@", script))
        os.chmod(launcher, 0o755)
        with open(os.path.join(base, "Contents/Info.plist"), "w") as fh:
            fh.write("""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleName</key><string>brewcat</string>
<key>CFBundleDisplayName</key><string>brewcat</string>
<key>CFBundleIdentifier</key><string>com.github.1985epma.brewcat</string>
<key>CFBundleVersion</key><string>%s</string>
<key>CFBundleShortVersionString</key><string>%s</string>
<key>CFBundleExecutable</key><string>brewcat</string>
<key>CFBundleIconFile</key><string>brewcat</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>NSHighResolutionCapable</key><true/>
</dict></plist>
""" % (VERSION, VERSION))
        with open(marker, "w") as fh:
            fh.write(want)
    return py_exe


def ensure_branded_launcher() -> None:
    """Re-launch through ~/Applications/brewcat.app so the process is named "brewcat" (not "Python")."""
    if sys.platform != "darwin" or os.environ.get("BREWCAT_BRANDED") or os.environ.get("BREWCAT_NO_APP"):
        return
    try:
        exe = build_app_bundle()
        if exe:
            os.environ["BREWCAT_BRANDED"] = "1"
            os.execv(exe, [exe, os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.py"),
                           *sys.argv[1:]])
    except Exception:  # noqa: BLE001 - branding is cosmetic; never block startup
        os.environ["BREWCAT_BRANDED"] = "1"
