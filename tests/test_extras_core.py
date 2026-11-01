"""extras_core is the Tk-free half of the Skills/MCP tabs: it must import and work without tkinter."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import extras_core as core

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_extras_core_imports_without_tkinter():
    code = ("import sys; sys.modules['tkinter'] = None; sys.modules['_tkinter'] = None; "
            "import extras_core as c; assert c.parse_repo('anthropics/skills')[0].startswith('https://')")
    r = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, timeout=60, check=False)
    assert r.returncode == 0, r.stderr


def test_trusted_sources_are_only_the_vetted_one():
    assert core.TRUSTED_SOURCES == {"anthropics/skills"}
    assert core.SKILL_PRESETS[0] in core.TRUSTED_SOURCES


def test_skill_root_per_target_and_scope(tmp_path):
    assert core.skill_root("claude", "project", tmp_path) == tmp_path / ".claude/skills"
    assert core.skill_root("kiro", "project", tmp_path) == tmp_path / ".kiro/skills"
    assert core.skill_root("vscode", "project", tmp_path) == tmp_path / ".github/skills"
    assert core.skill_root("vscode", "user", None) == Path.home() / ".copilot/skills"


def test_project_scope_without_a_folder_is_a_clear_error():
    with pytest.raises(ValueError, match="project folder"):
        core.skill_root("claude", "project", None)
    with pytest.raises(ValueError, match="project folder"):
        core.mcp_file("claude", "project", None)


def test_mcp_file_project_scope(tmp_path):
    assert core.mcp_file("claude", "project", tmp_path) == (tmp_path / ".mcp.json", "mcpServers")
    assert core.mcp_file("kiro", "project", tmp_path) == (tmp_path / ".kiro/settings/mcp.json", "mcpServers")
    assert core.mcp_file("vscode", "project", tmp_path) == (tmp_path / ".vscode/mcp.json", "servers")


def test_git_head_of_a_non_repo_is_empty(tmp_path):
    assert core.git_head(tmp_path) == ""


def test_is_preset_requires_exact_name_command_and_args():
    assert core.is_preset("memory", "npx", ["-y", "@modelcontextprotocol/server-memory"])
    assert not core.is_preset("memory", "sh", ["-y", "@modelcontextprotocol/server-memory"])
    assert not core.is_preset("memory", "npx", ["-y", "@modelcontextprotocol/server-memory", "--evil"])
    assert not core.is_preset("custom", "npx", ["-y", "@modelcontextprotocol/server-memory"])


def test_parse_env_ignores_items_without_equals():
    assert core.parse_env("A=1, B=x=y, junk, ") == {"A": "1", "B": "x=y"}
    assert core.parse_env("") == {}


def test_mcp_entry_kiro_has_no_type():
    assert core.mcp_entry("claude", "npx", ["-y", "x"], {}) == {"type": "stdio", "command": "npx", "args": ["-y", "x"]}
    assert core.mcp_entry("kiro", "npx", ["-y", "x"], {"K": "v"}) == {"command": "npx", "args": ["-y", "x"],
                                                                      "env": {"K": "v"}}


def test_add_mcp_server_merges_and_keeps_backup(tmp_path):
    f = tmp_path / "mcp.json"
    f.write_text(json.dumps({"mcpServers": {"old": {"command": "x"}}, "other": 1}))
    core.add_mcp_server(f, "mcpServers", "new", core.mcp_entry("claude", "uvx", ["mcp-server-time"], {}))
    data = json.loads(f.read_text())
    assert set(data["mcpServers"]) == {"old", "new"} and data["other"] == 1
    assert set(json.loads((tmp_path / "mcp.json.bak").read_text())["mcpServers"]) == {"old"}


def test_add_mcp_server_creates_missing_file_and_rejects_garbage(tmp_path):
    f = tmp_path / "sub/.mcp.json"
    core.add_mcp_server(f, "servers", "a", {"command": "x", "args": []})
    assert json.loads(f.read_text()) == {"servers": {"a": {"command": "x", "args": []}}}
    f.write_text("{not json")
    with pytest.raises(ValueError):
        core.add_mcp_server(f, "servers", "b", {})
    assert f.read_text() == "{not json"  # a corrupt config is never overwritten


def test_marks():
    assert core.marks({"claude": True, "vscode": True}) == "C · V"
    assert core.marks({}) == "· · ·"
