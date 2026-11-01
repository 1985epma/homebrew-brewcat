"""Ctrl-C during `brewcat install` must end cleanly: no traceback, exit code 130, no package-by-package retry."""
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

# Stands in for brew: `list` prints nothing (nothing installed); `install` records its pid and then blocks.
FAKE_BREW = """#!/bin/sh
case "$1" in
  list) exit 0 ;;
  install) echo $$ >> "$FAKE_BREW_PIDS"; exec sleep 60 ;;
esac
exit 0
"""

DRIVER = """
import signal, sys
signal.signal(signal.SIGINT, signal.default_int_handler)  # the test runner may have started us with SIGINT ignored
import cli
sys.exit(cli.run(sys.argv[1:]))
"""


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX signals")
def test_ctrl_c_during_install_cancels_without_traceback_or_retry(tmp_path):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    brew = bindir / "brew"
    brew.write_text(FAKE_BREW)
    brew.chmod(0o755)
    pids = tmp_path / "pids"
    env = dict(os.environ, PATH=f"{bindir}{os.pathsep}{os.environ['PATH']}", FAKE_BREW_PIDS=str(pids),
               BREWCAT_NO_APP="1", BREWCAT_BRANDED="1")
    # "git pro" is a multi-package kit, so a failed batch WOULD trigger the one-by-one retry.
    proc = subprocess.Popen([sys.executable, "-c", DRIVER, "install", "git pro", "--yes", "--platform", "mac"],
                            cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        deadline = time.time() + 20
        while not pids.exists() and time.time() < deadline:
            time.sleep(0.05)
        assert pids.exists(), "the fake brew install never started"
        child = int(pids.read_text().split()[0])
        # A terminal delivers Ctrl-C to the whole foreground group; killpg is not available everywhere, so
        # signal the CLI and its brew child one by one.
        os.kill(proc.pid, signal.SIGINT)
        try:
            os.kill(child, signal.SIGINT)
        except ProcessLookupError:
            pass
        out, err = proc.communicate(timeout=20)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.communicate()
    assert "Traceback" not in err, err
    assert "Cancelled." in err
    assert proc.returncode == 130
    assert "retrying" not in out
    assert len(pids.read_text().split()) == 1, "brew install must not be started again after Ctrl-C"


@pytest.mark.parametrize("exc", [KeyboardInterrupt, EOFError])
def test_interrupt_at_the_confirmation_prompt_cancels_cleanly(monkeypatch, capsys, exc):
    import brewenv
    import cli

    def interrupted(_prompt=""):
        raise exc

    monkeypatch.setattr(brewenv, "find_brew", lambda: "/nonexistent/brew")
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", interrupted)
    assert cli.run(["install", "jq"]) == 130
    assert "Cancelled." in capsys.readouterr().err
