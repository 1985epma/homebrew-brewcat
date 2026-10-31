import json

import pytest

import cli
from help_text import VERSION


def run(args, capsys):
    code = cli.run(args)
    out = capsys.readouterr()
    return code, out.out, out.err


def test_no_args_opens_the_gui():
    assert cli.run([]) is None


def test_version_help_and_psn_argument(capsys):
    code, out, _ = run(["--version"], capsys)
    assert code == 0 and out.startswith(f"brewcat {VERSION}")
    code, out, _ = run(["-h"], capsys)
    assert code == 0 and "USAGE" in out
    assert cli.run(["-psn_0_12345"]) is None  # old Finder launch argument is ignored


@pytest.mark.parametrize("args", [["--nope"], ["nope"], ["search", "--profile", "bogus"], ["install"]])
def test_invalid_usage_exits_2(args, capsys):
    with pytest.raises(SystemExit) as exc:
        cli.run(args)
    assert exc.value.code == 2
    assert "brewcat: error" in capsys.readouterr().err


def test_search_json_and_not_found(capsys):
    code, out, _ = run(["search", "terraform", "-p", "sre", "--platform", "mac", "--json"], capsys)
    assert code == 0 and any(i["name"].endswith("terraform") for i in json.loads(out))
    code, _, err = run(["search", "zzzzzz-nothing"], capsys)
    assert code == 1 and "nothing found" in err


def test_kits_listing_and_show(capsys):
    code, out, _ = run(["kits", "-p", "sre", "--json"], capsys)
    assert code == 0 and any(k["name"] == "Terraform + AWS" for k in json.loads(out))
    code, out, _ = run(["kits", "git pro", "--json"], capsys)
    assert code == 0 and len(json.loads(out)) == 6
    code, _, err = run(["kits", "no such kit"], capsys)
    assert code == 1 and "no kit matches" in err


def test_install_dry_run_prints_plan_and_runs_nothing(capsys, monkeypatch):
    monkeypatch.setattr(cli.subprocess, "run", lambda *a, **k: pytest.fail("must not run brew"))
    monkeypatch.setattr(cli, "_installed", lambda: {"formula": set(), "cask": set()})
    monkeypatch.setattr(cli.brewenv, "find_brew", lambda: "/x/brew")
    code, out, _ = run(["install", "git pro", "--dry-run", "--platform", "mac"], capsys)
    assert code == 0 and "brew install git gh lazygit git-delta git-lfs pre-commit" in out


def test_install_without_yes_and_without_terminal_refuses(capsys, monkeypatch):
    monkeypatch.setattr(cli, "_installed", lambda: {"formula": set(), "cask": set()})
    monkeypatch.setattr(cli.brewenv, "find_brew", lambda: "/x/brew")
    monkeypatch.setattr(cli.sys.stdin, "isatty", lambda: False, raising=False)
    monkeypatch.setattr(cli.subprocess, "run", lambda *a, **k: pytest.fail("must not run brew"))
    code, _, err = run(["install", "jq", "--platform", "mac"], capsys)
    assert code == 2 and "--yes" in err


def test_install_unknown_target(capsys):
    code, _, err = run(["install", "nonexistent-xyz", "-n"], capsys)
    assert code == 1 and "nothing called" in err


def test_export_to_stdout_and_file(capsys, tmp_path):
    code, out, _ = run(["export", "git pro", "--platform", "mac"], capsys)
    assert code == 0 and 'brew "git"' in out
    target = tmp_path / "Brewfile"
    code, _, _ = run(["export", "jq", "cask:obs", "--platform", "mac", "-o", str(target)], capsys)
    assert code == 0 and target.read_text() == 'brew "jq"\ncask "obs"\n'


def test_doctor_json_shape_and_exit_code(capsys):
    code, out, _ = run(["doctor", "--json"], capsys)
    data = json.loads(out)
    assert data["version"] == VERSION and {"name", "status", "detail", "hint"} <= set(data["checks"][0])
    assert code == (0 if data["ok"] else 1)


def test_doctor_reports_missing_tk_as_failure(capsys, monkeypatch):
    import builtins
    real = builtins.__import__

    def fake(name, *a, **k):
        if name == "tkinter":
            raise ImportError
        return real(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake)
    code, out, _ = run(["doctor", "--json"], capsys)
    assert code == 1 and any(c["name"] == "tk" and c["status"] == "FAIL" for c in json.loads(out)["checks"])


def test_cask_is_not_offered_on_linux(capsys):
    code, _, err = run(["export", "cask:obs", "--platform", "linux"], capsys)
    assert code == 1 and "linux" in err


def test_default_platform_follows_the_host(monkeypatch):
    monkeypatch.setattr(cli.sys, "platform", "linux")
    assert cli._default_platform() == "linux"
    monkeypatch.setattr(cli.sys, "platform", "darwin")
    assert cli._default_platform() == "mac"
