"""plan.build_plan / format_plan with a fake `brew` on disk: no real Homebrew, no network."""
import stat
import time

import catalog_data as cd
import plan

# Output copied from a real `brew install --dry-run` (stdout); warnings go to stderr and are not parsed.
DRY_RUN_JQ = """\
==> Would install 1 formula:
jq 1.8.2
==> Downloading https://ghcr.io/v2/homebrew/core/jq/manifests/1.8.2-1
Already downloaded: /Users/someone/Library/Caches/Homebrew/downloads/abc--jq-1.8.2-1.bottle_manifest.json
==> Would install 1 dependency for jq:
oniguruma 6.9.10
"""
DRY_RUN_MANY = """\
==> Would install 1 formula:
mpv 0.41.0_12
==> Would install 3 dependencies for mpv:
jpeg-turbo      3.2.1
libb2           0.98.1
libpng          1.6.59
"""
DRY_RUN_CASKS = "==> Would install 2 casks:\nfirefox vlc\n"


def make_brew(tmp_path, body):
    """A `brew` shell script; every call is appended to calls.log. `body` is the case arms for $1."""
    script = tmp_path / "brew"
    script.write_text(f'#!/bin/sh\necho "$@" >> "{tmp_path}/calls.log"\ncase "$1" in\n{body}\nesac\nexit 0\n')
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return str(script)


def calls(tmp_path):
    log = tmp_path / "calls.log"
    return log.read_text().splitlines() if log.exists() else []


def items(*keys):
    return [cd.BY_KEY[k] for k in keys]


def test_parse_dry_run_extracts_dependencies_only():
    assert plan.parse_dry_run(DRY_RUN_JQ, ["jq"]) == ["oniguruma"]
    assert plan.parse_dry_run(DRY_RUN_MANY, ["mpv"]) == ["jpeg-turbo", "libb2", "libpng"]
    assert plan.parse_dry_run(DRY_RUN_CASKS, ["firefox", "vlc"]) == []
    assert plan.parse_dry_run("", ["jq"]) == []
    # a requested package is never reported as its own dependency, also when requested as tap/name
    assert plan.parse_dry_run("==> Would install 2 dependencies for x:\nterraform 1.0\nfoo 2\n",
                              ["hashicorp/tap/terraform"]) == ["foo"]


def test_build_plan_classifies_and_lists_extra_dependencies(tmp_path):
    brew = make_brew(tmp_path, f"""\
list) case "$2" in --formula) printf 'git\\ngh\\n' ;; *) printf 'iterm2\\n' ;; esac ;;
outdated) printf 'gh\\niterm2\\n' ;;
install) case "$*" in *--cask*) printf '{DRY_RUN_CASKS}' ;; *) cat <<'EOF2'
{DRY_RUN_JQ}EOF2
;; esac ;;""")
    pl = plan.build_plan(brew, items("formula:git", "formula:gh", "formula:jq", "cask:iterm2", "cask:warp"))
    assert pl.to_install == ["jq", "warp"]
    assert pl.already_installed == ["git", "gh", "iterm2"]
    assert pl.outdated == ["gh", "iterm2"]
    assert pl.extra_deps == ["oniguruma"]
    assert pl.casks == ["iterm2", "warp"]
    assert any("1 cask(s)" in n and "administrator password" in n for n in pl.notes)
    log = calls(tmp_path)
    assert len(log) <= 5  # list x2, outdated, one dry run per kind: never one call per package
    assert "install --dry-run -- jq" in log and "install --dry-run --cask -- warp" in log


def test_build_plan_without_new_packages_makes_no_dry_run(tmp_path):
    brew = make_brew(tmp_path, "list) printf 'git\\n' ;;")
    pl = plan.build_plan(brew, items("formula:git"))
    assert pl.to_install == [] and pl.already_installed == ["git"] and pl.extra_deps == []
    assert not any("--dry-run" in c for c in calls(tmp_path))


def test_failed_dry_run_gives_a_note_and_no_dependencies(tmp_path):
    brew = make_brew(tmp_path, "list) ;;\ninstall) echo 'Error: boom' >&2; exit 1 ;;")
    pl = plan.build_plan(brew, items("formula:jq"))
    assert pl.to_install == ["jq"] and pl.extra_deps == []
    assert any("could not check dependencies" in n for n in pl.notes)


def test_failed_listing_is_reported_not_raised(tmp_path):
    brew = make_brew(tmp_path, "list) exit 1 ;;\ninstall) exit 1 ;;")
    pl = plan.build_plan(brew, items("formula:jq"))
    assert pl.to_install == ["jq"]
    assert any("could not read the installed formula list" in n for n in pl.notes)


def test_missing_brew_never_raises(tmp_path):
    pl = plan.build_plan(str(tmp_path / "no-such-brew"), items("formula:jq", "cask:warp"))
    assert pl.to_install == ["jq", "warp"] and pl.extra_deps == []
    assert any("could not check dependencies" in n for n in pl.notes)


def test_timeout_is_reported_not_raised(tmp_path):
    brew = make_brew(tmp_path, "list) ;;\ninstall) exec sleep 30 ;;")
    start = time.time()
    pl = plan.build_plan(brew, items("formula:jq"), timeout=0.5)
    assert time.time() - start < 10
    assert pl.extra_deps == [] and any("could not check dependencies" in n for n in pl.notes)


def test_format_plan_is_plain_text_and_invents_no_numbers():
    note = "1 cask(s): the installer may ask for your administrator password"
    pl = plan.Plan(["jq", "warp"], ["git"], ["git"], ["oniguruma"], [note], ["warp"])
    text = plan.format_plan(pl)
    first = text.splitlines()[0]
    assert first == "Summary: 2 to install, 1 extra dependency, 1 already installed, 1 outdated."
    assert "\x1b" not in text
    for name in ("jq", "warp", "oniguruma", "git", "administrator password"):
        assert name in text
    for word in ("MB", "GB", "minute", "second", "~"):
        assert word not in text


def test_format_plan_truncates_long_dependency_lists():
    deps = [f"dep{n}" for n in range(plan.MAX_LISTED + 5)]
    text = plan.format_plan(plan.Plan(["x"], [], [], deps, []))
    assert "and 5 more" in text and f"dep{plan.MAX_LISTED + 4}" not in text
    assert text.splitlines()[0] == f"Summary: 1 to install, {len(deps)} extra dependencies."


def test_format_plan_empty():
    assert plan.format_plan(plan.Plan([], [], [], [], [])) == "Summary: 0 to install."
