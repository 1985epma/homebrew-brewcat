"""Homebrew/hardware detection shared by the GUI and the CLI (no tkinter import)."""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from typing import Callable, List, Optional, Sequence

BREW_CANDIDATES = [
    "/opt/homebrew/bin/brew",
    "/usr/local/bin/brew",
    "/home/linuxbrew/.linuxbrew/bin/brew",
    os.path.expanduser("~/.linuxbrew/bin/brew"),
]


def find_brew() -> Optional[str]:
    return shutil.which("brew") or next((p for p in BREW_CANDIDATES if os.path.exists(p)), None)


def apple_silicon() -> bool:
    """True on Apple Silicon hardware, even when this process runs translated under Rosetta."""
    if sys.platform != "darwin":
        return False
    if platform.machine() == "arm64":
        return True
    try:
        return subprocess.run(["/usr/sbin/sysctl", "-n", "hw.optional.arm64"], capture_output=True,
                              text=True, timeout=5, check=False).stdout.strip() == "1"
    except (OSError, subprocess.SubprocessError):
        return False


def brew_command(brew: str, *args: str) -> list:
    """Full argv to run brew. Package names go after "--" so a name can never be read as an option, and
    on Apple Silicon brew runs in the architecture of its prefix: a plain `brew` started from a process
    translated by Rosetta fails with "Cannot install under Rosetta 2 in ARM default prefix"."""
    if args and args[0] in ("install", "uninstall", "reinstall"):
        opts = [a for a in args[1:] if a.startswith("-")]
        names = [a for a in args[1:] if not a.startswith("-")]
        args = (args[0], *opts, "--", *names)
    if apple_silicon() and os.path.exists("/usr/bin/arch"):
        if brew.startswith("/opt/homebrew"):
            return ["/usr/bin/arch", "-arm64", brew, *args]
        if brew.startswith("/usr/local"):
            return ["/usr/bin/arch", "-x86_64", brew, *args]
    return [brew, *args]


def install_with_retry(run: Callable[[List[str]], int], args: Sequence[str],
                       on_retry: Callable[[], None] = lambda: None) -> int:
    """Run `brew install a b c` (args = ["install", ...flags, "a", "b", "c"]) through `run`, which executes a
    brew argument list and returns its exit code. If the batch fails, retry package by package so one bad
    package cannot block the others (brew skips the ones already installed). Returns the worst exit code.
    The same policy is used by the window and the command line."""
    code = run(list(args))
    names = [a for a in args[1:] if not a.startswith("-")]
    if code == 0 or args[0] != "install" or len(names) < 2:
        return code
    on_retry()
    flags = [a for a in args[1:] if a.startswith("-")]
    return max(run(["install", *flags, name]) for name in names)
