import json
import os

import pytest

import extras_tab as e


@pytest.mark.parametrize("spec", [
    "anthropics/skills", "https://github.com/anthropics/skills",
    "https://github.com/anthropics/skills/tree/main/skills", "git@github.com:a/b.git",
    "ssh://git@github.com/a/b.git", "https://example.com/r.git"])
def test_parse_repo_accepts(spec):
    url, _branch, _sub = e.parse_repo(spec)
    assert url.startswith(("https://", "ssh://", "git@"))


@pytest.mark.parametrize("spec", [
    "", "-x", "--upload-pack=touch /tmp/x", "ext::sh -c id", "file:///etc", "a/b c",
    "ssh://-oProxyCommand/x", "git@-evil:a/b", "ssh://u@-evil/x", "https://github.com/a/b/tree/-bad/x"])
def test_parse_repo_rejects(spec):
    with pytest.raises(ValueError):
        e.parse_repo(spec)


def test_parse_repo_branch_and_subpath():
    assert e.parse_repo("https://github.com/o/r/tree/main/skills/x") == ("https://github.com/o/r.git", "main", "skills/x")


def test_unsafe_links_detects_symlink_leaving_the_skill(tmp_path):
    (tmp_path / "SKILL.md").write_text("x")
    os.symlink("/etc/hosts", tmp_path / "leak")
    os.symlink("SKILL.md", tmp_path / "inside")
    assert [p.name for p in e.unsafe_links(tmp_path)] == ["leak"]


def test_skill_scripts_lists_executable_content(tmp_path):
    (tmp_path / "SKILL.md").write_text("x")
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts/run.sh").write_text("echo")
    (tmp_path / "notes.txt").write_text("plain")
    assert e.skill_scripts(tmp_path) == ["scripts/run.sh"]


def test_parse_skill_folded_description(tmp_path):
    (tmp_path / "SKILL.md").write_text("---\nname: demo\ndescription: >\n  line one\n  line two\n---\nbody")
    assert e.parse_skill(tmp_path) == ("demo", "line one line two")


def test_scan_skills_ignores_symlinked_dirs(tmp_path):
    real = tmp_path / "real"
    (real / "a").mkdir(parents=True)
    (real / "a/SKILL.md").write_text("---\nname: a\n---\n")
    root = tmp_path / "root"
    root.mkdir()
    os.symlink(real, root / "link")
    assert e.scan_skills(root) == []


def test_write_json_keeps_backup_and_read_json_rejects_garbage(tmp_path):
    f = tmp_path / "mcp.json"
    f.write_text(json.dumps({"mcpServers": {"a": {}}}))
    e.write_json(f, {"mcpServers": {"a": {}, "b": {}}})
    assert json.loads(f.read_text())["mcpServers"].keys() == {"a", "b"}
    assert json.loads((tmp_path / "mcp.json.bak").read_text())["mcpServers"].keys() == {"a"}
    f.write_text("{not json")
    with pytest.raises(ValueError):
        e.read_json(f)


def test_every_mcp_preset_is_well_formed():
    for name, command, args, desc, _env in e.MCP_PRESETS:
        assert name and command and desc
        assert e.shlex.split(args)
