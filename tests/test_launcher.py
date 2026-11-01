import os
import re
import stat
import subprocess

import pytest

import launcher
from help_text import VERSION

FAKE_STUB = "#!/bin/sh\nexit 0\n"


@pytest.fixture
def home(tmp_path, monkeypatch):
    h = tmp_path / "home"
    h.mkdir()
    monkeypatch.setenv("HOME", str(h))
    monkeypatch.delenv("BREWCAT_HIDDEN_APP", raising=False)
    return h


def _marker(home, body):
    m = home / "Applications/brewcat.app/Contents/.brewcat-build"
    m.parent.mkdir(parents=True)
    m.write_text(body)


# ───────────────────────── bundle_state ─────────────────────────
def test_bundle_state_healthy(home, tmp_path):
    stub = tmp_path / "Python"
    stub.write_text(FAKE_STUB)
    _marker(home, f"{VERSION}|{stub}|/x/app.py")
    assert launcher.bundle_state() is None


def test_bundle_state_marker_missing(home):
    assert "marker missing" in launcher.bundle_state()


def test_bundle_state_marker_malformed(home):
    _marker(home, "garbage")
    assert "marker missing" in launcher.bundle_state()


def test_bundle_state_stub_removed(home, tmp_path):
    _marker(home, f"{VERSION}|{tmp_path}/gone/Python|/x/app.py")
    assert "removed" in launcher.bundle_state()


# ───────────────────────── LAUNCHER_SCRIPT ─────────────────────────
def _script(hidden=""):
    return launcher.LAUNCHER_SCRIPT.replace("@HIDDEN@", hidden).replace("@SCRIPT@", "/some/app.py")


def test_script_has_no_placeholder_left():
    assert not re.search(r"@[A-Z_]+@", _script())
    assert "@HIDDEN@" in launcher.LAUNCHER_SCRIPT and "@SCRIPT@" in launcher.LAUNCHER_SCRIPT


@pytest.mark.parametrize("hidden", ["", "export BREWCAT_HIDDEN_APP=1\n"])
def test_script_is_valid_bash(tmp_path, hidden):
    f = tmp_path / "brewcat"
    f.write_text(_script(hidden))
    assert subprocess.run(["bash", "-n", str(f)], capture_output=True, text=True, check=False).returncode == 0


# ───────────────────────── build_app_bundle ─────────────────────────
@pytest.fixture
def fake_python_home(tmp_path, monkeypatch, home):
    """A base_prefix that contains a fake Python.app stub, so build_app_bundle works on any OS."""
    prefix = tmp_path / "prefix"
    stub = prefix / "Resources/Python.app/Contents/MacOS/Python"
    stub.parent.mkdir(parents=True)
    stub.write_text(FAKE_STUB)
    stub.chmod(0o755)
    monkeypatch.setattr(launcher.sys, "base_prefix", str(prefix))
    return home


def test_build_app_bundle_visible_by_default(fake_python_home):
    exe = launcher.build_app_bundle()
    base = fake_python_home / "Applications/brewcat.app"
    assert exe == str(base / "Contents/MacOS/brewcat-python")
    script = (base / "Contents/MacOS/brewcat").read_text()
    assert "BREWCAT_HIDDEN_APP" not in script and not re.search(r"@[A-Z_]+@", script)
    assert os.stat(base / "Contents/MacOS/brewcat").st_mode & stat.S_IXUSR
    assert launcher.bundle_state() is None  # what it just built is healthy


def test_build_app_bundle_hidden_exports_the_variable(fake_python_home, monkeypatch):
    monkeypatch.setenv("BREWCAT_HIDDEN_APP", "1")
    exe = launcher.build_app_bundle()
    base = fake_python_home / "Library/Application Support/brewcat/brewcat.app"
    assert exe == str(base / "Contents/MacOS/brewcat-python")
    assert "export BREWCAT_HIDDEN_APP=1\n" in (base / "Contents/MacOS/brewcat").read_text()
    assert not (fake_python_home / "Applications/brewcat.app").exists()


def test_build_app_bundle_is_not_rebuilt_when_up_to_date(fake_python_home):
    launcher.build_app_bundle()
    script = fake_python_home / "Applications/brewcat.app/Contents/MacOS/brewcat"
    script.write_text("sentinel")
    launcher.build_app_bundle()
    assert script.read_text() == "sentinel"


def test_build_app_bundle_without_python_stub_returns_none(home, tmp_path, monkeypatch):
    monkeypatch.setattr(launcher.sys, "base_prefix", str(tmp_path / "nothing"))
    assert launcher.build_app_bundle() is None


# ───────────────────────── running the generated script ─────────────────────────
def _exe(path, body):
    path.write_text("#!/bin/sh\n" + body)
    path.chmod(0o755)
    return path


def _run_launcher(tmp_path, stub_body, py_fallback_body=None, args=("--flag",)):
    """Write the launcher next to a fake brewcat-python and run it. The hard-coded Homebrew python paths are swapped
    for a fake so the test never depends on (or touches) what is installed on this machine."""
    macos = tmp_path / "MacOS"
    macos.mkdir()
    log = tmp_path / "log"
    _exe(macos / "brewcat-python", stub_body)
    fallback = tmp_path / "fallback-python3"
    if py_fallback_body is not None:
        _exe(fallback, py_fallback_body)
    text = _script().replace("/opt/homebrew/bin/python3 /usr/local/bin/python3", str(fallback))
    text = text.replace("/usr/bin/osascript", str(tmp_path / "osascript"))
    _exe(tmp_path / "osascript", f'echo "dialog" >> "{log}"\n')
    launcher_file = macos / "brewcat"
    launcher_file.write_text(text)
    launcher_file.chmod(0o755)
    res = subprocess.run([str(launcher_file), *args], capture_output=True, text=True, check=False,
                         env={"PATH": "/usr/bin:/bin"})
    return res, log


def test_script_uses_bundled_python_when_it_works(tmp_path):
    echo = f'echo "stub branded=$BREWCAT_BRANDED args=$*" > "{tmp_path}/out"\n'
    res, _ = _run_launcher(tmp_path, 'case "$1" in -c) exit 0 ;; esac\n' + echo,
                           py_fallback_body=f'echo fallback > "{tmp_path}/out"\n')
    assert res.returncode == 0, res.stderr
    assert (tmp_path / "out").read_text().strip() == "stub branded=1 args=/some/app.py --flag"


def test_script_falls_back_when_bundled_python_is_broken(tmp_path):
    """After `brew upgrade python` + cleanup the copied stub cannot load: `-c "import tkinter"` fails."""
    res, log = _run_launcher(
        tmp_path, "exit 1\n",
        py_fallback_body=f'echo "fallback branded=${{BREWCAT_BRANDED:-unset}} args=$*" > "{tmp_path}/out"\n')
    assert res.returncode == 0, res.stderr
    assert (tmp_path / "out").read_text().strip() == "fallback branded=unset args=/some/app.py --flag"
    assert not log.exists()  # no dialog needed


def test_script_shows_install_dialog_when_no_python_works(tmp_path):
    res, log = _run_launcher(tmp_path, "exit 1\n", py_fallback_body=None)
    assert log.read_text().strip() == "dialog"
