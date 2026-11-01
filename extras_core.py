"""Pure logic behind the Skills and MCP tabs (no tkinter, so it is testable and usable on a box without Tk)."""
from __future__ import annotations

import json
import os
import platform
import re
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple

HOME = Path.home()
TARGETS = [("claude", "Claude"), ("kiro", "Kiro"), ("vscode", "VS Code")]
SKILL_PRESETS = ["anthropics/skills"]
TRUSTED_SOURCES = {"anthropics/skills"}
SCRIPT_EXTS = {".sh", ".bash", ".zsh", ".py", ".js", ".mjs", ".ts", ".rb", ".pl", ".ps1", ".command"}
SKIP_DIRS = {".git", "node_modules", "__pycache__"}

# name, command, args, description, env hint
MCP_PRESETS = [
    ("filesystem", "npx", "-y @modelcontextprotocol/server-filesystem /path/to/allow",
     "Read/write files in the directories you allow", ""),
    ("memory", "npx", "-y @modelcontextprotocol/server-memory", "Persistent knowledge-graph memory", ""),
    ("sequential-thinking", "npx", "-y @modelcontextprotocol/server-sequential-thinking",
     "Step-by-step reasoning tool", ""),
    ("context7", "npx", "-y @upstash/context7-mcp", "Up-to-date library docs in your prompts", ""),
    ("playwright", "npx", "@playwright/mcp@latest", "Browser automation with Playwright", ""),
    ("fetch", "uvx", "mcp-server-fetch", "Fetch web pages and convert them to Markdown", ""),
    ("git", "uvx", "mcp-server-git", "Read and manipulate git repositories", ""),
    ("time", "uvx", "mcp-server-time", "Current time and timezone conversion", ""),
]


# ───────────────────────── paths ─────────────────────────
def skill_root(target: str, scope: str, project: Optional[Path]) -> Path:
    base = HOME if scope == "user" else project
    if base is None:
        raise ValueError("a project folder is required for project scope")
    sub = {"claude": ".claude/skills", "kiro": ".kiro/skills",
           "vscode": ".copilot/skills" if scope == "user" else ".github/skills"}[target]
    return Path(base) / sub


def mcp_file(target: str, scope: str, project: Optional[Path]) -> Tuple[Path, str]:
    if scope == "user":
        code_user = (HOME / "Library/Application Support/Code/User" if platform.system() == "Darwin"
                     else HOME / ".config/Code/User")
        return {"claude": (HOME / ".claude.json", "mcpServers"),
                "kiro": (HOME / ".kiro/settings/mcp.json", "mcpServers"),
                "vscode": (code_user / "mcp.json", "servers")}[target]
    if project is None:
        raise ValueError("a project folder is required for project scope")
    p = Path(project)
    return {"claude": (p / ".mcp.json", "mcpServers"),
            "kiro": (p / ".kiro/settings/mcp.json", "mcpServers"),
            "vscode": (p / ".vscode/mcp.json", "servers")}[target]


def read_json(path: Path) -> dict:
    if not path.exists() or not path.read_text().strip():
        return {}
    return json.loads(path.read_text())


def write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        shutil.copy2(path, path.with_name(path.name + ".bak"))
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n")
    os.replace(tmp, path)


# ───────────────────────── skills ─────────────────────────
def parse_skill(folder: Path) -> Tuple[str, str]:
    text = (folder / "SKILL.md").read_text(errors="replace")
    meta = {}
    m = re.match(r"---\s*\n(.*?)\n---", text, re.S)
    if m:
        lines = m.group(1).splitlines()
        for i, line in enumerate(lines):
            if ":" in line and not line.startswith(" "):
                k, v = line.split(":", 1)
                v = v.strip().strip("\"'")
                if v in (">", "|", ">-", "|-"):
                    block = []
                    for nxt in lines[i + 1:]:
                        if nxt.startswith(" "):
                            block.append(nxt.strip())
                        else:
                            break
                    v = " ".join(block)
                meta[k.strip()] = v
    return meta.get("name") or folder.name, meta.get("description", "")


def scan_skills(root: Path, depth: int = 4) -> List[Path]:
    found: List[Path] = []

    def walk(d: Path, level: int) -> None:
        if (d / "SKILL.md").is_file():
            found.append(d)
            return
        if level >= depth:
            return
        for c in sorted(d.iterdir()):
            if c.is_dir() and not c.is_symlink() and c.name not in SKIP_DIRS:
                walk(c, level + 1)

    walk(root, 0)
    return found


def parse_repo(spec: str) -> Tuple[str, Optional[str], str]:
    """'owner/repo', a GitHub URL or a /tree/<branch>/<sub> URL → (clone_url, branch, subpath).

    Raises ValueError for anything that is not a plain GitHub shorthand or an http(s)/ssh git URL, so
    user-typed text can never be interpreted by git as an option or an exotic transport (ext::, file:)."""
    spec = spec.strip().rstrip("/")
    if not spec or spec.startswith("-") or any(c in spec for c in " \t\r\n\0"):
        raise ValueError("Invalid source: use owner/repo, a GitHub URL or a local folder")
    m = re.match(r"(?:https?://github\.com/)?([\w.-]+/[\w.-]+?)(?:\.git)?(?:/tree/([^/]+)(?:/(.*))?)?$", spec)
    if m:
        branch = m.group(2)
        if branch and branch.startswith("-"):
            raise ValueError("Invalid branch name")
        return f"https://github.com/{m.group(1)}.git", branch, m.group(3) or ""
    if re.match(r"(https://|ssh://|git@)[\w.@:/~-]+$", spec):
        rest = re.sub(r"^(https://|ssh://|git@)", "", spec)
        host = rest.rsplit("@", 1)[-1]
        if rest.startswith("-") or host.startswith("-"):  # ssh would read it as an option
            raise ValueError("Invalid source host")
        return spec, None, ""
    raise ValueError("Invalid source: use owner/repo, a GitHub URL or a local folder")


def skill_scripts(folder: Path) -> List[str]:
    """Executable content shipped with a skill (scripts or files with the exec bit)."""
    out = []
    for p in sorted(folder.rglob("*")):
        if p.is_file() and not p.is_symlink() and ".git" not in p.parts:
            if p.suffix.lower() in SCRIPT_EXTS or p.stat().st_mode & 0o111:
                out.append(str(p.relative_to(folder)))
    return out


def git_head(path: Path) -> str:
    try:
        return subprocess.run(["git", "-C", str(path), "rev-parse", "HEAD"], capture_output=True,
                              text=True, timeout=15, check=False).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def unsafe_links(folder: Path) -> List[Path]:
    """Symlinks inside `folder` that point outside of it (they could expose files such as ~/.ssh keys)."""
    root = folder.resolve()
    bad = []
    for p in folder.rglob("*"):
        if p.is_symlink():
            try:
                p.resolve().relative_to(root)
            except (ValueError, OSError, RuntimeError):
                bad.append(p)
    return bad


def marks(flags: Dict[str, bool]) -> str:
    return " ".join(label[0] if flags.get(k) else "·" for k, label in TARGETS)


def is_preset(name: str, command: str, args: List[str]) -> bool:
    """True when (name, command, args) is exactly one of brewcat's built-in MCP presets."""
    return any(p[0] == name and p[1] == command and shlex.split(p[2]) == args for p in MCP_PRESETS)


def parse_env(text: str) -> Dict[str, str]:
    """'A=1, B=2' -> {'A': '1', 'B': '2'}; items without '=' are ignored."""
    return dict(p.split("=", 1) for p in (s.strip() for s in text.split(",")) if "=" in p)


def mcp_entry(target: str, command: str, args: List[str], env: Dict[str, str]) -> Dict[str, object]:
    """The server definition as each tool wants it (Kiro has no "type" field)."""
    entry: Dict[str, object] = {"type": "stdio", "command": command, "args": args}
    if env:
        entry["env"] = env
    return {k: v for k, v in entry.items() if k != "type"} if target == "kiro" else entry


def add_mcp_server(path: Path, key: str, name: str, entry: Dict[str, object]) -> None:
    """Merge one server into the JSON config at `path` under `key` (a .bak copy of the old file is kept)."""
    data = read_json(path)
    data.setdefault(key, {})[name] = entry
    write_json(path, data)
