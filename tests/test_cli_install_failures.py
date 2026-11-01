"""`brewcat install` failure summary: which packages failed and the exact command to retry only those."""
import stat

import cli

# Fake brew: nothing installed, dry runs are quiet; real installs fail for every package named in $FAIL.
FAKE_BREW = """#!/bin/sh
case "$1" in
  list|outdated) exit 0 ;;
  install)
    case "$*" in *--dry-run*) exit 0 ;; esac
    echo "$@" >> "$CALLS"
    for a in "$@"; do
      for f in $FAIL; do [ "$a" = "$f" ] && exit 1; done
    done
    exit 0 ;;
esac
exit 0
"""


def setup(tmp_path, monkeypatch, fail):
    brew = tmp_path / "brew"
    brew.write_text(FAKE_BREW)
    brew.chmod(brew.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setattr(cli.brewenv, "find_brew", lambda: str(brew))
    monkeypatch.setenv("FAIL", " ".join(fail))
    monkeypatch.setenv("CALLS", str(tmp_path / "calls"))


def calls(tmp_path):
    log = tmp_path / "calls"
    return log.read_text().splitlines() if log.exists() else []


def test_failed_packages_are_listed_with_a_retry_command(tmp_path, monkeypatch, capsys):
    setup(tmp_path, monkeypatch, ["gh", "lazygit"])
    assert cli.run(["install", "git pro", "--yes", "--platform", "mac"]) == 1
    err = capsys.readouterr().err
    assert "Failed: gh, lazygit" in err
    assert "  brew install gh lazygit" in err
    assert "git-delta" not in err.split("Failed:")[1]  # the ones that worked are not blamed
    log = calls(tmp_path)
    assert log[0].startswith("install -- git gh lazygit") and "install -- gh" in log  # batch first, then one by one


def test_single_package_failure(tmp_path, monkeypatch, capsys):
    setup(tmp_path, monkeypatch, ["jq"])
    assert cli.run(["install", "jq", "--yes", "--platform", "mac"]) == 1
    err = capsys.readouterr().err
    assert "Failed: jq" in err and "brew install jq" in err


def test_failed_casks_are_retried_with_the_cask_flag(tmp_path, monkeypatch, capsys):
    setup(tmp_path, monkeypatch, ["warp"])
    assert cli.run(["install", "cask:warp", "--yes", "--platform", "mac"]) == 1
    assert "brew install --cask warp" in capsys.readouterr().err


def test_mixed_kinds_get_one_retry_line_each(tmp_path, monkeypatch, capsys):
    setup(tmp_path, monkeypatch, ["jq", "visual-studio-code"])
    assert cli.run(["install", "Web Full-Stack", "--yes", "--platform", "mac"]) == 1
    err = capsys.readouterr().err
    assert "Failed: jq, visual-studio-code" in err
    assert "  brew install jq\n" in err and "  brew install --cask visual-studio-code\n" in err


def test_success_prints_no_failure_summary(tmp_path, monkeypatch, capsys):
    setup(tmp_path, monkeypatch, [])
    assert cli.run(["install", "jq", "--yes", "--platform", "mac"]) == 0
    assert "Failed" not in capsys.readouterr().err
