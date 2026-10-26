"""macOS launcher bundle: gives brewcat its own name and icon in Dock, menu bar and Launchpad.

No tkinter import here so it can run in headless/CLI contexts."""
from __future__ import annotations

import os
import re
import shutil
import sys
from typing import Optional

from help_text import VERSION


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
    if not (os.path.exists(py_exe) and os.path.exists(launcher) and os.path.exists(marker)
            and open(marker).read() == want):
        shutil.rmtree(base, ignore_errors=True)
        os.makedirs(macos)
        os.makedirs(os.path.join(base, "Contents/Resources"))
        shutil.copy2(stub, py_exe)
        for icns in (os.path.join(here, "assets/brewcat.icns"), os.path.join(here, "brewcat.icns")):
            if os.path.exists(icns):
                shutil.copy2(icns, os.path.join(base, "Contents/Resources/brewcat.icns"))
                break
        with open(launcher, "w") as fh:  # what Finder/Launchpad run on double-click
            fh.write(f'#!/bin/bash\nexport BREWCAT_BRANDED=1 TK_SILENCE_DEPRECATION=1\n'
                     f'exec "$(dirname "$0")/brewcat-python" "{script}" "$@"\n')
        os.chmod(launcher, 0o755)
        with open(os.path.join(base, "Contents/Info.plist"), "w") as fh:
            fh.write("""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleName</key><string>brewcat</string>
<key>CFBundleDisplayName</key><string>brewcat</string>
<key>CFBundleIdentifier</key><string>com.github.1985epma.brewcat</string>
<key>CFBundleExecutable</key><string>brewcat</string>
<key>CFBundleIconFile</key><string>brewcat</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>NSHighResolutionCapable</key><true/>
</dict></plist>
""")
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
