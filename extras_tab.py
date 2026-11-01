"""Skills and MCP server installers for Claude, Kiro and VS Code (the Tk widgets; the logic is in extras_core)."""
from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import tempfile
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Dict, List, Optional, Tuple

from extras_core import (MCP_PRESETS, SKILL_PRESETS, TARGETS, TRUSTED_SOURCES, add_mcp_server, git_head, is_preset,
                         marks, mcp_entry, mcp_file, parse_env, parse_repo, parse_skill, read_json, scan_skills,
                         skill_root, skill_scripts, unsafe_links)


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
                    r = subprocess.run(cmd, capture_output=True, text=True, timeout=180, check=False,
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
        warn = "" if is_preset(name, command, args) else ("\n\n⚠ Custom command (not one of brewcat's built-in presets). It will run on "
                                 "your machine, with your permissions, whenever your AI tool starts this server. "
                                 "Only continue if you trust where it came from.")
        if not messagebox.askyesno("Confirm installation", f"Add MCP server '{name}'\n"
                                   f"{command} {' '.join(args)}{warn}\n\nto:\n{files}"):
            return
        env = parse_env(self.f["env"].get())
        if not shutil.which(command):
            self.app._log("err", f"Warning: '{command}' not found in PATH (install it first).\n")
        for k in targets:
            path, key = mcp_file(k, scope, proj)
            try:
                add_mcp_server(path, key, name, mcp_entry(k, command, args, env))
                self.app._log("info", f"✓ {name} → {path}\n")
            except (OSError, ValueError) as exc:
                self.app._log("err", f"✗ {path}: {exc}\n")
        self.refresh_marks()
