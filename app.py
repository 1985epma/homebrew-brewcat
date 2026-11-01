#!/usr/bin/env python3
"""brewcat: visual package catalog for devs and gamers (macOS and Linux).

Entry point. Everything that does not need a window (--help, --version, doctor, search, list, install…)
runs from cli.py without importing tkinter, so the CLI also works on a headless box without python3-tk."""
from __future__ import annotations

import sys
from typing import List, Optional

import cli
import launcher


def main(argv: Optional[List[str]] = None) -> None:
    code = cli.run(argv)  # --help, --version, doctor, --install-app… run without opening a window
    if code is not None:
        sys.exit(code)
    try:
        import gui  # noqa: PLC0415 - imports tkinter, so only when a window is really wanted
    except ModuleNotFoundError as exc:
        if (exc.name or "").split(".")[0] not in ("tkinter", "_tkinter"):
            raise
        print("brewcat: the window needs Tk, which this Python does not have.\n"
              "  macOS / Homebrew: brew install python-tk\n"
              "  Debian/Ubuntu:    sudo apt install python3-tk\n"
              "  Fedora:           sudo dnf install python3-tkinter\n"
              "The command line works without it: try `brewcat doctor`, `brewcat search jq`, `brewcat --help`.",
              file=sys.stderr)
        sys.exit(1)
    gui._reexec_with_modern_tk()
    launcher.ensure_branded_launcher()
    try:
        gui.App().mainloop()
    except gui.tk.TclError as exc:
        print(f"brewcat: cannot open a window ({exc}).\n"
              "No display available? Run `brewcat doctor` to diagnose.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
