"""Opens the real window (skipped when there is no display, e.g. a headless Linux box without xvfb)."""
import os
import time

import pytest

tk = pytest.importorskip("tkinter")


@pytest.fixture
def window():
    import gui as app
    try:
        win = app.App()
    except tk.TclError as exc:
        if "display" not in str(exc):  # a real Tk error (e.g. a cursor name that only exists on macOS) must fail
            raise
        pytest.skip(f"no display: {exc}")
    win.update()
    yield win
    try:
        win.destroy()
    except tk.TclError:
        pass  # the test already closed it


def test_every_profile_and_category_renders(window):
    import gui as app
    for label, _ in app.PROFILES:
        window.profile.set(label)
        window._on_profile()
        for cat in window.cat_entries:
            window.category = cat
            window.refresh()
    window.profile.set("All")
    window._on_profile()
    assert len(window.tree.get_children()) > 0


def test_help_and_about_open(window):
    window.show_help()
    window.show_about()
    window.update()
    assert len([w for w in window.winfo_children() if w.winfo_class() == "Toplevel"]) == 2


def test_search_filters_the_list(window):
    window.category = "★ All"
    window.search.set("terraform")
    window.refresh()
    names = [window.tree.item(i)["values"][1] for i in window.tree.get_children()]
    assert "terraform" in names and "git" not in names


class FakeRunner:
    def __init__(self):
        self.terminated = 0

    def terminate(self):
        self.terminated += 1


def test_closing_an_idle_window_just_destroys_it(window, monkeypatch):
    import gui as app
    destroyed = []
    monkeypatch.setattr(window, "destroy", lambda: destroyed.append(1))
    monkeypatch.setattr(app.messagebox, "askyesno", lambda *a, **k: pytest.fail("must not ask when idle"))
    window.runner = FakeRunner()
    window._on_close()
    assert destroyed == [1] and window.runner.terminated == 1  # terminate() is a harmless no-op when idle


def test_closing_during_an_install_asks_and_can_be_cancelled(window, monkeypatch):
    import gui as app
    destroyed, asked = [], []
    monkeypatch.setattr(window, "destroy", lambda: destroyed.append(1))
    monkeypatch.setattr(app.messagebox, "askyesno", lambda title, msg: asked.append(msg) or False)
    window.runner = FakeRunner()
    window.busy = True
    window._on_close()
    assert asked and "still running" in asked[0]
    assert destroyed == [] and window.runner.terminated == 0


def test_closing_during_an_install_stops_the_brew_child(window, monkeypatch, tmp_path):
    if os.name != "posix":
        pytest.skip("needs a shell script as the fake brew")
    import gui as app
    fake_brew = tmp_path / "brew"
    fake_brew.write_text("#!/bin/sh\necho started\nsleep 60\n")
    fake_brew.chmod(0o755)
    monkeypatch.setattr(app, "ensure_askpass", lambda: None)  # do not write into the real home
    monkeypatch.setattr(app.messagebox, "askyesno", lambda *a, **k: True)
    destroyed = []
    monkeypatch.setattr(window, "destroy", lambda: destroyed.append(1))
    window.brew = str(fake_brew)
    window.run_brew([["update"]])
    end = time.time() + 10
    while not window.runner.running and time.time() < end:
        time.sleep(0.02)
    assert window.runner.running and window.busy
    window._on_close()
    assert not window.runner.running and destroyed == [1]
