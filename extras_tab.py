"""Skills and MCP server installers for Claude, Kiro and VS Code."""
from __future__ import annotations

import json
import os
import platform
import re
import shlex
import shutil
import subprocess
import tempfile
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
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
                              text=True, timeout=15).stdout.strip()
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


# ───────────────────────── widgets ─────────────────────────
class TargetBar(ttk.LabelFrame):
    def __init__(self, master, **kw):
        super().__init__(master, text="Install to", padding=8, **kw)
        self.vars = {k: tk.BooleanVar(value=(k == "claude")) for k, _ in TARGETS}
        for k, label in TARGETS:
            ttk.Checkbutton(self, text=label, variable=self.vars[k]).pack(side="left", padx=4)
        self.scope = tk.StringVar(value="user")
        ttk.Separator(self, orient="vertical").pack(side="left", fill="y", padx=8)
        ttk.Radiobutton(self, text="User (global)", value="user", variable=self.scope).pack(side="left")
        ttk.Radiobutton(self, text="Project", value="project", variable=self.scope).pack(side="left", padx=4)
        self.project: Optional[Path] = None
        self.proj_lbl = ttk.Label(self, text="(no folder)", foreground="#666666")
        ttk.Button(self, text="Folder…", command=self.pick).pack(side="left", padx=4)
        self.proj_lbl.pack(side="left")

    def pick(self) -> None:
        d = filedialog.askdirectory(title="Project folder")
        if d:
            self.project = Path(d)
            self.proj_lbl.config(text=self.project.name)
            self.scope.set("project")

    def selected(self) -> Optional[Tuple[List[str], str, Optional[Path]]]:
        targets = [k for k, v in self.vars.items() if v.get()]
        if not targets:
            messagebox.showinfo("Install", "Select at least one target (Claude, Kiro or VS Code).")
            return None
        if self.scope.get() == "project" and not self.project:
            self.pick()
            if not self.project:
                return None
        return targets, self.scope.get(), self.project


def marks(flags: Dict[str, bool]) -> str:
    return " ".join(label[0] if flags.get(k) else "·" for k, label in TARGETS)


# ───────────────────────── skills tab ─────────────────────────
class SkillsTab(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master, padding=10)
        self.app = app
        self.tmp: Optional[str] = None
        self.scanned_spec = ""
        self.scanned_commit = ""
        self.skills: Dict[str, Path] = {}

        src = ttk.Frame(self)
        src.pack(fill="x")
        ttk.Label(src, text="Source (GitHub repo/URL or local folder):").pack(side="left")
        self.source = ttk.Combobox(src, values=SKILL_PRESETS, width=48)
        self.source.set(SKILL_PRESETS[0])
        self.source.pack(side="left", padx=6)
        ttk.Button(src, text="Browse…", command=self.browse).pack(side="left")
        ttk.Button(src, text="Scan", command=self.scan).pack(side="left", padx=6)

        cols = ("name", "installed", "desc")
        self.tree = ttk.Treeview(self, columns=cols, show="headings", selectmode="extended")
        for c, t, w in [("name", "Skill", 200), ("installed", "C K V", 70), ("desc", "Description", 640)]:
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, stretch=(c == "desc"))
        self.tree.pack(fill="both", expand=True, pady=8)

        self.bar = TargetBar(self)
        self.bar.pack(fill="x")
        ttk.Label(self, text="C = Claude, K = Kiro, V = VS Code. Shows where each skill is already installed "
                             "for the selected scope.", style="Sub.TLabel").pack(anchor="w", pady=4)
        ttk.Button(self, text="Install selected skills", command=self.install).pack(anchor="e")

    def browse(self) -> None:
        d = filedialog.askdirectory(title="Folder with skills")
        if d:
            self.source.set(d)

    def scan(self) -> None:
        spec = self.source.get().strip()
        if not spec:
            return
        self.app._log("info", f"\nScanning skills from {spec} …\n")

        def worker() -> None:
            try:
                self.scanned_spec, self.scanned_commit = spec, ""
                if Path(spec).expanduser().is_dir():
                    root = Path(spec).expanduser()
                else:
                    url, branch, sub = parse_repo(spec)
                    tmp = tempfile.mkdtemp(prefix="brewcat-skills-")
                    cmd = ["git", "clone", "--depth", "1"] + (["--branch", branch] if branch else []) \
                        + ["--", url, tmp]
                    r = subprocess.run(cmd, capture_output=True, text=True, timeout=180,
                                       env=dict(os.environ, GIT_TERMINAL_PROMPT="0"))
                    if r.returncode:
                        raise RuntimeError(r.stderr.strip() or "git clone failed")
                    self.tmp = tmp
                    self.scanned_commit = git_head(Path(tmp))
                    root = (Path(tmp) / sub).resolve()
                    root.relative_to(Path(tmp).resolve())  # a "../" sub-path must not leave the clone
                found = scan_skills(root)
                items = [(f, *parse_skill(f)) for f in found]
                self.app.log_q.put(("call", lambda: self.show(items)))
            except Exception as exc:  # noqa: BLE001
                self.app.log_q.put(("err", f"Scan failed: {exc}\n"))

        threading.Thread(target=worker, daemon=True).start()

    def show(self, items) -> None:
        self.tree.delete(*self.tree.get_children())
        self.skills.clear()
        for folder, name, desc in items:
            iid = self.tree.insert("", "end", values=(name, "", desc))
            self.skills[iid] = folder
        self.refresh_marks()
        self.app._log("info", f"Found {len(items)} skill(s).\n")

    def refresh_marks(self) -> None:
        scope, proj = self.bar.scope.get(), self.bar.project
        for iid, folder in self.skills.items():
            flags = {}
            for k, _ in TARGETS:
                if scope == "project" and not proj:
                    continue
                flags[k] = (skill_root(k, scope, proj) / folder.name).exists()
            self.tree.set(iid, "installed", marks(flags))

    def install(self) -> None:
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Skills", "Select one or more skills first (scan a source).")
            return
        picked = self.bar.selected()
        if not picked:
            return
        targets, scope, proj = picked
        names = ", ".join(self.skills[i].name for i in sel)
        dests = "\n".join(str(skill_root(k, scope, proj)) for k in targets)
        trusted = self.scanned_spec in TRUSTED_SOURCES
        lines = [f"Install skill(s): {names}", f"Source: {self.scanned_spec or 'local folder'}"
                 + (f" @ {self.scanned_commit[:10]}" if self.scanned_commit else "")]
        if not trusted:
            lines.append("⚠ This source is not in brewcat's trusted list. A skill is a set of instructions "
                         "(and sometimes scripts) your AI tool will follow. Review it before installing.")
        for i in sel:
            scripts = skill_scripts(self.skills[i])
            if scripts:
                shown = ", ".join(scripts[:6]) + (f" … (+{len(scripts) - 6})" if len(scripts) > 6 else "")
                lines.append(f"⚠ {self.skills[i].name} ships {len(scripts)} script(s): {shown}")
        lines += ["", "into:", dests]
        if not messagebox.askyesno("Confirm installation", "\n".join(lines)):
            return
        for iid in sel:
            folder = self.skills[iid]
            links = unsafe_links(folder)
            if links:
                self.app._log("err", f"✗ {folder.name}: skipped, symlink(s) point outside the skill folder: "
                                     f"{', '.join(str(link.relative_to(folder)) for link in links[:5])}\n")
                continue
            for k in targets:
                dest = skill_root(k, scope, proj) / folder.name
                if dest.exists() and not messagebox.askyesno("Overwrite", f"{dest}\nalready exists. Replace it?"):
                    continue
                try:
                    if dest.exists():
                        shutil.rmtree(dest)
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copytree(folder, dest, symlinks=True, ignore=shutil.ignore_patterns(".git"))
                    with open(dest / ".brewcat-source.json", "w") as fh:
                        json.dump({"source": self.scanned_spec, "commit": self.scanned_commit,
                                   "installed_by": "brewcat"}, fh, indent=2)
                    self.app._log("info", f"✓ {folder.name} → {dest}\n")
                except OSError as exc:
                    self.app._log("err", f"✗ {folder.name} → {dest}: {exc}\n")
        self.refresh_marks()


# ───────────────────────── MCP tab ─────────────────────────
class McpTab(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master, padding=10)
        self.app = app

        self.tree = ttk.Treeview(self, columns=("name", "cmd", "installed", "desc"), show="headings",
                                 selectmode="browse", height=9)
        for c, t, w in [("name", "Server", 160), ("cmd", "Command", 80), ("installed", "C K V", 70),
                        ("desc", "Description", 600)]:
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, stretch=(c == "desc"))
        self.tree.pack(fill="x")
        for name, cmd, args, desc, _ in MCP_PRESETS:
            self.tree.insert("", "end", iid=name, values=(name, cmd, "", desc))
        self.tree.bind("<<TreeviewSelect>>", self.fill)

        form = ttk.LabelFrame(self, text="Server definition (edit freely or type your own)", padding=8)
        form.pack(fill="x", pady=8)
        self.f = {k: tk.StringVar() for k in ("name", "command", "args", "env")}
        for r, (k, label) in enumerate([("name", "Name"), ("command", "Command"),
                                        ("args", "Arguments"), ("env", "Env (KEY=VALUE, comma-separated)")]):
            ttk.Label(form, text=label).grid(row=r, column=0, sticky="w", padx=(0, 8), pady=2)
            ttk.Entry(form, textvariable=self.f[k], width=80).grid(row=r, column=1, sticky="ew", pady=2)
        form.columnconfigure(1, weight=1)

        self.bar = TargetBar(self)
        self.bar.pack(fill="x")
        ttk.Label(self, text="Edits the MCP config of each target (a .bak copy is kept). "
                             "Needs node (npx) or uv (uvx) installed — get them in the Packages tab.",
                  style="Sub.TLabel", wraplength=900).pack(anchor="w", pady=4)
        ttk.Button(self, text="Install MCP server", command=self.install).pack(anchor="e")
        self.refresh_marks()

    def fill(self, _e=None) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        for name, cmd, args, _d, env in MCP_PRESETS:
            if name == sel[0]:
                self.f["name"].set(name)
                self.f["command"].set(cmd)
                self.f["args"].set(args)
                self.f["env"].set(env)

    def refresh_marks(self) -> None:
        scope, proj = self.bar.scope.get(), self.bar.project
        for name, *_ in MCP_PRESETS:
            flags = {}
            for k, _ in TARGETS:
                if scope == "project" and not proj:
                    continue
                path, key = mcp_file(k, scope, proj)
                try:
                    flags[k] = name in read_json(path).get(key, {})
                except (OSError, ValueError):
                    flags[k] = False
            self.tree.set(name, "installed", marks(flags))

    def install(self) -> None:
        name, command = self.f["name"].get().strip(), self.f["command"].get().strip()
        if not name or not command:
            messagebox.showinfo("MCP", "Pick a server or fill in name and command.")
            return
        picked = self.bar.selected()
        if not picked:
            return
        targets, scope, proj = picked
        try:
            args = shlex.split(self.f["args"].get())
        except ValueError as exc:
            messagebox.showerror("MCP", f"Invalid arguments: {exc}")
            return
        files = "\n".join(str(mcp_file(k, scope, proj)[0]) for k in targets)
        known = any(p[0] == name and p[1] == command and shlex.split(p[2]) == args for p in MCP_PRESETS)
        warn = "" if known else ("\n\n⚠ Custom command (not one of brewcat's built-in presets). It will run on "
                                 "your machine, with your permissions, whenever your AI tool starts this server. "
                                 "Only continue if you trust where it came from.")
        if not messagebox.askyesno("Confirm installation", f"Add MCP server '{name}'\n"
                                   f"{command} {' '.join(args)}{warn}\n\nto:\n{files}"):
            return
        env = dict(p.split("=", 1) for p in (s.strip() for s in self.f["env"].get().split(",")) if "=" in p)
        if not shutil.which(command):
            self.app._log("err", f"Warning: '{command}' not found in PATH (install it first).\n")
        entry = {"type": "stdio", "command": command, "args": args}
        if env:
            entry["env"] = env
        for k in targets:
            path, key = mcp_file(k, scope, proj)
            try:
                data = read_json(path)
                data.setdefault(key, {})[name] = (
                    {k2: v for k2, v in entry.items() if k2 != "type"} if k == "kiro" else entry)
                write_json(path, data)
                self.app._log("info", f"✓ {name} → {path}\n")
            except (OSError, ValueError) as exc:
                self.app._log("err", f"✗ {path}: {exc}\n")
        self.refresh_marks()
