import pytest

import brewenv


def test_names_go_after_double_dash(monkeypatch):
    monkeypatch.setattr(brewenv, "apple_silicon", lambda: False)
    assert brewenv.brew_command("/x/brew", "install", "--cask", "foo") == ["/x/brew", "install", "--cask", "--", "foo"]
    assert brewenv.brew_command("/x/brew", "uninstall", "bar") == ["/x/brew", "uninstall", "--", "bar"]
    assert brewenv.brew_command("/x/brew", "list", "--formula", "-1") == ["/x/brew", "list", "--formula", "-1"]


def test_option_looking_name_cannot_become_an_option(monkeypatch):
    monkeypatch.setattr(brewenv, "apple_silicon", lambda: False)
    cmd = brewenv.brew_command("/x/brew", "install", "--cask", "good")
    assert cmd.index("--") < cmd.index("good")


def test_runs_native_arch_on_apple_silicon(monkeypatch):
    monkeypatch.setattr(brewenv, "apple_silicon", lambda: True)
    monkeypatch.setattr(brewenv.os.path, "exists", lambda p: p == "/usr/bin/arch")
    assert brewenv.brew_command("/opt/homebrew/bin/brew", "list")[:3] == ["/usr/bin/arch", "-arm64", "/opt/homebrew/bin/brew"]
    assert brewenv.brew_command("/usr/local/bin/brew", "list")[:2] == ["/usr/bin/arch", "-x86_64"]


# ───────────────────────── install_with_retry ─────────────────────────
class _Runner:
    """Fake `run(args) -> exit code`: records every call; `fail` is a set of package names whose install fails."""

    def __init__(self, fail=(), batch_fails=None):
        self.calls = []
        self.fail = set(fail)
        self.batch_fails = bool(self.fail) if batch_fails is None else batch_fails

    def __call__(self, args):
        self.calls.append(list(args))
        names = [a for a in args[1:] if not a.startswith("-")]
        if len(names) > 1:
            return 1 if self.batch_fails else 0
        return 1 if any(n in self.fail for n in names) else 0


def test_retry_batch_ok_runs_once():
    run, retried = _Runner(), []
    assert brewenv.install_with_retry(run, ["install", "a", "b", "c"], lambda: retried.append(1)) == 0
    assert run.calls == [["install", "a", "b", "c"]] and not retried


def test_retry_batch_fails_then_each_package_and_worst_code(capsys):
    codes = {"a": 0, "b": 3, "c": 1}
    calls = []

    def run(args):
        calls.append(list(args))
        return 1 if len(args) > 2 else codes[args[-1]]

    retried = []
    assert brewenv.install_with_retry(run, ["install", "a", "b", "c"], lambda: retried.append(1)) == 3
    assert calls == [["install", "a", "b", "c"], ["install", "a"], ["install", "b"], ["install", "c"]]
    assert retried == [1]  # announced once, before the per-package pass


def test_retry_all_packages_ok_after_failed_batch_returns_zero():
    run = _Runner(batch_fails=True)
    assert brewenv.install_with_retry(run, ["install", "a", "b"]) == 0
    assert len(run.calls) == 3


def test_retry_single_package_is_not_retried():
    run, retried = _Runner(fail={"a"}), []
    assert brewenv.install_with_retry(run, ["install", "a"], lambda: retried.append(1)) == 1
    assert run.calls == [["install", "a"]] and not retried


@pytest.mark.parametrize("cmd", ["uninstall", "upgrade", "reinstall", "list"])
def test_retry_only_applies_to_install(cmd):
    run, retried = _Runner(batch_fails=True), []
    assert brewenv.install_with_retry(run, [cmd, "a", "b"], lambda: retried.append(1)) == 1
    assert run.calls == [[cmd, "a", "b"]] and not retried


def test_retry_keeps_flags_on_every_package():
    run = _Runner(batch_fails=True)
    brewenv.install_with_retry(run, ["install", "--cask", "--force", "a", "b"])
    assert run.calls == [["install", "--cask", "--force", "a", "b"],
                         ["install", "--cask", "--force", "a"], ["install", "--cask", "--force", "b"]]


def test_retry_does_not_mutate_the_arguments():
    args = ["install", "a", "b"]
    brewenv.install_with_retry(_Runner(batch_fails=True), args)
    assert args == ["install", "a", "b"]


def test_retry_default_on_retry_is_a_noop():
    assert brewenv.install_with_retry(_Runner(batch_fails=True), ["install", "a", "b"]) == 0
