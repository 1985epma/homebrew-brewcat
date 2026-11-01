"""`brewcat doctor --report`: Markdown for a GitHub issue, redacted, and usable without Homebrew."""
import os
import socket

import pytest

import cli
from help_text import VERSION

USER = "zelda-secret-user"
HOST = "hyrule-castle-host"


@pytest.fixture
def private_machine(tmp_path, monkeypatch):
    home = tmp_path / "home" / USER
    home.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    for var in ("USER", "LOGNAME", "USERNAME"):
        monkeypatch.setenv(var, USER)
    monkeypatch.setenv("SECRET_TOKEN", "hunter2-token-value")
    monkeypatch.setattr(socket, "gethostname", lambda: HOST)
    monkeypatch.setattr(cli.brewenv, "find_brew", lambda: None)
    return home


def test_report_leaks_no_home_user_host_or_environment(private_machine, tmp_path):
    text = cli.diagnostic_report()
    for secret in (str(private_machine), str(tmp_path), USER, HOST, "hunter2", "SECRET_TOKEN"):
        assert secret not in text, secret
    assert text.startswith("### brewcat diagnostics")


def test_redaction_replaces_paths_inside_check_details(private_machine, monkeypatch):
    monkeypatch.setattr(cli, "collect_checks", lambda: [
        cli._check("python", cli.OK, f"3.9 ({private_machine}/venv/bin/python)", f"cd {private_machine} && fix {USER}")])
    text = cli.diagnostic_report()
    assert "~/venv/bin/python" in text and "<user>" in text
    assert str(private_machine) not in text and USER not in text


def test_report_has_versions_and_checks_without_brew(private_machine):
    text = cli.diagnostic_report()
    assert f"- brewcat: {VERSION}" in text
    for label in ("- OS: ", "- Architecture: ", "- Python: ", "- Tk: ", "- Homebrew: not found"):
        assert label in text
    assert "[FAIL] homebrew: brew not found" in text and "fix: Install Homebrew" in text
    assert text.count("```") == 2  # one fenced block with the checks


def test_doctor_report_flag_prints_markdown_and_wins_over_json(private_machine, capsys):
    assert cli.run(["doctor", "--report", "--json"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("### brewcat diagnostics") and not out.lstrip().startswith("{")
    assert USER not in out and str(private_machine) not in out


def test_report_works_when_the_user_name_is_unknown(private_machine, monkeypatch):
    def boom():
        raise KeyError("no such user")

    monkeypatch.setattr(cli.getpass, "getuser", boom)
    monkeypatch.setattr(socket, "gethostname", lambda: (_ for _ in ()).throw(OSError("no host")))
    for var in ("USER", "LOGNAME", "USERNAME"):
        monkeypatch.delenv(var, raising=False)
    assert "brewcat diagnostics" in cli.diagnostic_report()
    assert os.environ["HOME"] == str(private_machine)
