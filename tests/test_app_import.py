import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _brewcat_without_tk(*args):
    """Run the real entry point in a Python where tkinter cannot be imported (a headless box without python3-tk)."""
    code = ("import sys; sys.modules['tkinter'] = None; sys.modules['_tkinter'] = None; "
            f"sys.argv = ['brewcat'] + {list(args)!r}; import app; app.main()")
    return subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, timeout=60)


@pytest.mark.parametrize("args", [("--version",), ("search", "jq"), ("list", "--profile", "sre"),
                                  ("install", "jq", "--dry-run"), ("kits",)])
def test_cli_works_without_tkinter(args):
    r = _brewcat_without_tk(*args)
    assert "Traceback" not in r.stderr, r.stderr
    assert r.returncode == 0, r.stderr + r.stdout


def test_window_without_tkinter_explains_instead_of_crashing():
    r = _brewcat_without_tk()
    assert r.returncode == 1
    assert "Traceback" not in r.stderr
    assert "needs Tk" in r.stderr and "brewcat doctor" in r.stderr


def test_importing_app_has_no_side_effects():
    sys.argv = ["brewcat", "--definitely-not-a-flag"]  # would exit(2) if import parsed arguments
    import app
    assert callable(app.main)
