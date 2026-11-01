"""GUI flows without a real brew: first-run welcome, install confirmation with the plan, failure handling.

Modal dialogs are driven through their buttons; App.wait_window is the only blocking call and is patched.
Plan and brew are fakes, so nothing here runs Homebrew or touches the real home directory."""
import sys
import time
import types

import pytest

tk = pytest.importorskip("tkinter")


@pytest.fixture
def window(monkeypatch, tmp_path):
    monkeypatch.setenv("BREWCAT_NO_WELCOME", "1")
    import gui as app
    monkeypatch.setattr(app, "config_dir", lambda: str(tmp_path / "cfg"))  # one-time flags go to a temp dir
    monkeypatch.setattr(app, "ensure_askpass", lambda: None)
    monkeypatch.setattr(app.App, "refresh_installed", lambda self: None)  # would run `brew list`
    try:
        win = app.App()
    except tk.TclError as exc:
        if "display" not in str(exc):
            raise
        pytest.skip(f"no display: {exc}")
    win.update()
    yield win
    try:
        win.destroy()
    except tk.TclError:
        pass


def pump(win, cond, timeout=10.0):
    end = time.time() + timeout
    while not cond() and time.time() < end:
        win.update()
        time.sleep(0.01)
    assert cond(), "timed out waiting for the window"


class FakeRunner:
    """Stands in for BrewRunner: `bad` package names exit 1, everything else 0."""

    def __init__(self, bad=(), cancelled=False):
        self.bad = set(bad)
        self.cancelled = cancelled
        self.calls = []

    def reset(self):
        pass

    def terminate(self):
        pass

    def run(self, argv, on_line, env=None):
        names = argv[argv.index("--") + 1:] if "--" in argv else []
        self.calls.append(list(argv))
        code = 1 if self.bad & set(names) else 0
        on_line("info", f"-> exit code {code}\n")
        return code


def fake_plan(monkeypatch, text="Plan: 2 to install", calls=None):
    mod = types.ModuleType("plan")

    def build_plan(brew, items, timeout=60.0):
        if calls is not None:
            calls.append((brew, [i.key for i in items]))
        return object()

    mod.build_plan = build_plan
    mod.format_plan = lambda plan: text
    monkeypatch.setitem(sys.modules, "plan", mod)


def run_batch(win, runner, cmds):
    win.brew = "/fake/brew"
    win.runner = runner
    win.run_brew(cmds)
    pump(win, lambda: not win.busy)


# ───────────────────────── first-run welcome ─────────────────────────
def test_welcome_appears_once_and_writes_the_flag(window, monkeypatch):
    import gui as app
    monkeypatch.delenv("BREWCAT_NO_WELCOME")
    shown = []
    monkeypatch.setattr(app.App, "wait_window", lambda self, w: (shown.append(w), w.skip()))
    monkeypatch.setattr(window, "run_brew", lambda *a: pytest.fail("the welcome must never install"))
    import os
    assert not os.path.exists(window.welcome_flag())
    assert window._maybe_welcome() is True
    assert os.path.exists(window.welcome_flag()) and len(shown) == 1
    assert window._maybe_welcome() is False and len(shown) == 1  # second launch: nothing


def test_welcome_flag_is_written_even_when_closed_with_the_window_button(window, monkeypatch):
    import os
    import gui as app
    monkeypatch.delenv("BREWCAT_NO_WELCOME")
    monkeypatch.setattr(app.App, "wait_window", lambda self, w: w.close())
    window._maybe_welcome()
    assert os.path.exists(window.welcome_flag())


def test_no_welcome_env_var_suppresses_it(window, monkeypatch):
    import os
    import gui as app
    monkeypatch.setenv("BREWCAT_NO_WELCOME", "1")
    monkeypatch.setattr(app.App, "wait_window", lambda self, w: pytest.fail("welcome must not open"))
    assert window._maybe_welcome() is False
    assert not os.path.exists(window.welcome_flag())


def test_welcome_starter_kit_switches_to_kits_and_selects_the_first(window, monkeypatch):
    import gui as app
    import catalog_data as cd
    monkeypatch.delenv("BREWCAT_NO_WELCOME")

    def choose(self, dlg):
        dlg.profile.set("QA")
        dlg.show_kit()

    monkeypatch.setattr(app.App, "wait_window", choose)
    monkeypatch.setattr(window, "run_brew", lambda *a: pytest.fail("the welcome must never install"))
    window._maybe_welcome()
    window.update()
    assert window.profile.get() == "QA" and window.category == app.KITS
    obj, _ = window.selected()
    assert isinstance(obj, cd.Kit) and obj.profile == cd.QA
    assert window.tree.selection()[0] == window.tree.get_children()[0]
    assert window.cat_entries[window.cat_list.curselection()[0]] == app.KITS


# ───────────────────────── confirmation with the plan ─────────────────────────
def pick_first_kit(window):
    window.show_starter_kits("Dev")
    obj, _ = window.selected()
    return obj


def test_install_confirmation_shows_the_plan_and_runs_on_accept(window, monkeypatch):
    import gui as app
    calls, shown, ran = [], [], []
    fake_plan(monkeypatch, "Plan: 3 to install", calls)
    window.brew = "/fake/brew"
    kit = pick_first_kit(window)

    def accept(self, dlg):
        shown.append(dlg.text.get("1.0", "end"))
        dlg.btn_ok.invoke()

    monkeypatch.setattr(app.App, "wait_window", accept)
    monkeypatch.setattr(app.messagebox, "askyesno", lambda *a, **k: pytest.fail("the plan dialog replaces it"))
    monkeypatch.setattr(window, "run_brew", lambda cmds: ran.append(cmds))
    window.install_selected()
    assert window.status_var.get() == "Checking what will change…" and window._planning
    pump(window, lambda: ran)
    assert calls == [("/fake/brew", [i.key for i in window.kit_items(kit)])]
    assert "Plan: 3 to install" in shown[0] and "brew install" in shown[0]
    assert ran[0][0][0] == "install"
    assert not window._planning and window.status_var.get() == ""


def test_cancel_in_the_plan_dialog_installs_nothing(window, monkeypatch):
    import gui as app
    ran, asked = [], []
    fake_plan(monkeypatch)
    window.brew = "/fake/brew"
    window.cart.add("formula:git")
    monkeypatch.setattr(app.App, "wait_window", lambda self, dlg: (asked.append(1), dlg.btn_cancel.invoke()))
    monkeypatch.setattr(window, "run_brew", lambda cmds: ran.append(cmds))
    window.install_cart()
    pump(window, lambda: asked)
    window.update()
    assert ran == []


def test_confirmation_falls_back_when_the_plan_fails(window, monkeypatch):
    import gui as app
    ran, asked = [], []
    mod = types.ModuleType("plan")

    def boom(*a, **k):
        raise RuntimeError("brew exploded")

    mod.build_plan, mod.format_plan = boom, boom
    monkeypatch.setitem(sys.modules, "plan", mod)
    window.brew = "/fake/brew"
    window.cart.add("formula:git")
    monkeypatch.setattr(app.messagebox, "askyesno", lambda title, msg: asked.append(msg) or True)
    monkeypatch.setattr(app.App, "wait_window", lambda self, dlg: pytest.fail("no plan, no plan dialog"))
    monkeypatch.setattr(window, "run_brew", lambda cmds: ran.append(cmds))
    window.install_cart()
    pump(window, lambda: ran)
    assert asked and asked[0].startswith("Install 1 packages?") and "git" in asked[0]
    assert ran == [[["install", "git"]]]


def test_confirmation_falls_back_when_plan_module_is_missing(window, monkeypatch):
    import gui as app
    ran, asked = [], []
    monkeypatch.setitem(sys.modules, "plan", None)  # import raises ImportError
    window.brew = "/fake/brew"
    window.cart.add("formula:git")
    monkeypatch.setattr(app.messagebox, "askyesno", lambda title, msg: asked.append(msg) or False)
    monkeypatch.setattr(window, "run_brew", lambda cmds: ran.append(cmds))
    window.install_cart()
    pump(window, lambda: asked)
    assert ran == []  # the user said no: still never installs without confirmation


def test_without_brew_the_plain_confirmation_is_used_synchronously(window, monkeypatch):
    import gui as app
    asked = []
    window.brew = None
    window.cart.add("formula:git")
    monkeypatch.setattr(app.messagebox, "askyesno", lambda title, msg: asked.append(msg) or False)
    window.install_cart()
    assert len(asked) == 1 and not window._planning


# ───────────────────────── failure tracking ─────────────────────────
def test_batch_result_marks_only_the_failed_packages():
    from gui import BatchResult
    r = BatchResult()
    r.record(["install", "a", "b", "c"], 1)  # the batch failed ...
    r.record(["install", "a"], 0)  # ... then package by package
    r.record(["install", "b"], 1)
    r.record(["install", "c"], 0)
    assert r.failed_installs() == ["b"] and r.succeeded() == ["a", "c"]
    assert r.retry_commands() == [["install", "b"]]


def test_batch_result_single_package_failure_and_cask_flags():
    from gui import BatchResult
    r = BatchResult()
    r.record(["install", "--cask", "app"], 1)
    r.record(["install", "tool"], 1)
    r.record(["install", "--cask", "app2"], 1)
    r.record(["update"], 1)
    assert r.failed_installs() == ["app", "tool", "app2"]
    assert r.retry_commands() == [["install", "--cask", "app", "app2"], ["install", "tool"]]
    assert r.failed_other() == ["brew update"]


def test_failed_batch_enables_retry_and_retry_reruns_only_the_failed(window, monkeypatch):
    import gui as app
    runner = FakeRunner(bad={"bad"})
    run_batch(window, runner, [["install", "good", "bad"]])
    assert window.failed_cmds == [["install", "bad"]]
    assert "bad" in window.status_var.get() and "1 package failed" in window.status_var.get()
    assert "Retry failed" in window.log.get("1.0", "end")
    assert str(window.btn_retry.cget("state")) == "normal"

    # Retry goes through the same confirmation (plan unavailable -> plain dialog) and runs only "bad".
    asked = []
    mod = types.ModuleType("plan")
    mod.build_plan = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no plan"))
    monkeypatch.setitem(sys.modules, "plan", mod)
    monkeypatch.setattr(app.messagebox, "askyesno", lambda title, msg: asked.append(msg) or True)
    before = len(runner.calls)
    window.retry_failed()
    pump(window, lambda: len(runner.calls) > before and not window.busy)
    assert asked and "bad" in asked[0] and "good" not in asked[0]
    new = runner.calls[before:]
    assert new and all("good" not in c for c in new)
    assert window.failed_cmds == [["install", "bad"]]  # still failing, still retryable


def test_retry_asks_for_confirmation_and_cancel_runs_nothing(window, monkeypatch):
    import gui as app
    runner = FakeRunner(bad={"bad"})
    run_batch(window, runner, [["install", "bad"]])
    monkeypatch.setattr(app.messagebox, "askyesno", lambda *a, **k: False)
    mod = types.ModuleType("plan")
    mod.build_plan = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no plan"))
    monkeypatch.setitem(sys.modules, "plan", mod)
    before = len(runner.calls)
    window.retry_failed()
    time.sleep(0.2)
    window.update()
    assert len(runner.calls) == before


def test_success_shows_a_one_line_summary_with_the_count(window):
    run_batch(window, FakeRunner(), [["install", "a", "b"], ["install", "--cask", "c"]])
    assert window.failed_cmds == []
    assert window.status_var.get() == "✓ 3 packages installed successfully."
    assert str(window.btn_retry.cget("state")) == "disabled"


def test_cancelled_run_is_not_a_failure_to_retry(window):
    run_batch(window, FakeRunner(bad={"x"}, cancelled=True), [["install", "x"]])
    assert window.failed_cmds == [] and window.status_var.get() == "Stopped."
    assert str(window.btn_retry.cget("state")) == "disabled"


def test_copy_log_puts_the_log_on_the_clipboard(window):
    window._log("info", "hello log\n")
    window.copy_log()
    assert "hello log" in window.clipboard_get()


# ───────────────────────── diagnostics ─────────────────────────
def test_copy_diagnostics_copies_the_report(window, monkeypatch):
    import cli
    import gui as app
    told = []
    monkeypatch.setattr(cli, "diagnostic_report", lambda: "REPORT BODY", raising=False)
    monkeypatch.setattr(app.messagebox, "showinfo", lambda title, msg: told.append(msg))
    window.copy_diagnostics()
    assert window.clipboard_get() == "REPORT BODY" and told == ["Copied. Paste it in your issue."]


def test_copy_diagnostics_reports_when_unavailable(window, monkeypatch):
    import cli
    import gui as app
    told = []
    monkeypatch.delattr(cli, "diagnostic_report", raising=False)
    monkeypatch.setattr(app.messagebox, "showinfo", lambda title, msg: told.append(msg))
    window.copy_diagnostics()
    assert told and "not available" in told[0]


def test_help_window_has_the_copy_diagnostics_button(window):
    window.show_help()
    window.update()

    def walk(w):
        yield w
        for c in w.winfo_children():
            yield from walk(c)

    texts = [str(w.cget("text")) for w in walk(window) if w.winfo_class() == "TButton"]
    assert "Copy diagnostics" in texts
