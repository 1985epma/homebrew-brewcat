#!/usr/bin/env python3
"""brewcat: visual package catalog for devs and gamers (macOS and Linux)."""
from __future__ import annotations

import os
import platform
import queue
import shutil
import subprocess
import sys
import threading
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, ttk
from typing import Dict, List, Optional, Set, Tuple

import catalog_data as cd
from extras_tab import McpTab, SkillsTab

os.environ.setdefault("TK_SILENCE_DEPRECATION", "1")


def _reexec_with_modern_tk() -> None:
    """The system Python's Tk 8.5 renders a blank window on recent macOS; use Homebrew's python-tk."""
    if tk.TkVersion >= 8.6 or os.environ.get("BREWCAT_REEXEC"):
        return
    for py in ("/opt/homebrew/bin/python3", "/usr/local/bin/python3",
               "/home/linuxbrew/.linuxbrew/bin/python3"):
        if os.path.exists(py) and os.path.realpath(py) != os.path.realpath(sys.executable):
            os.environ["BREWCAT_REEXEC"] = "1"
            os.execv(py, [py, *sys.argv])
    print("Warning: Tk < 8.6 detected; the window may be blank. Run: brew install python-tk",
          file=sys.stderr)


_reexec_with_modern_tk()

SYSTEM = cd.MAC if platform.system() == "Darwin" else cd.LINUX
BREW_CANDIDATES = [
    "/opt/homebrew/bin/brew",
    "/usr/local/bin/brew",
    "/home/linuxbrew/.linuxbrew/bin/brew",
    os.path.expanduser("~/.linuxbrew/bin/brew"),
]

ALL, SUGGEST, KITS, CART = "★ All", "✨ Suggestions", "📦 Kits", "🛒 My list"
PROFILES = [("All", None), ("Dev", cd.DEV), ("Gamer", cd.GAMER)]


def find_brew() -> Optional[str]:
    return shutil.which("brew") or next((p for p in BREW_CANDIDATES if os.path.exists(p)), None)


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("brewcat")
        self.geometry("1180x720")
        self.minsize(960, 600)

        self.brew = find_brew()
        self.installed: Dict[str, Set[str]] = {"formula": set(), "cask": set()}
        self.cart: Set[str] = set()
        self.busy = False
        self.log_q: "queue.Queue[Tuple[str, object]]" = queue.Queue()
        self.rows: Dict[str, object] = {}  # iid -> Item | Kit
        self.reasons: Dict[str, str] = {}

        self.profile = tk.StringVar(value="All")
        self.platform = tk.StringVar(value=SYSTEM)
        self.search = tk.StringVar()
        self.category = ALL

        self._build_ui()
        self.search.trace_add("write", lambda *_: self.refresh())
        self.after(100, self._poll_log)
        self.refresh_installed()

    # ───────────────────────── UI ─────────────────────────
    def _build_ui(self) -> None:
        style = ttk.Style(self)
        style.configure("Title.TLabel", font=("TkDefaultFont", 16, "bold"))
        style.configure("Sub.TLabel", foreground="#666666")
        style.configure("Treeview", rowheight=24)

        top = ttk.Frame(self, padding=(10, 8))
        top.pack(fill="x")
        ttk.Label(top, text="🍺 brewcat", style="Title.TLabel").pack(side="left")
        ttk.Label(top, text=f"  {'macOS' if SYSTEM == cd.MAC else 'Linux'}"
                            f" • {'brew found' if self.brew else 'brew NOT found'}",
                  style="Sub.TLabel").pack(side="left")
        ttk.Button(top, text="Refresh status", command=self.refresh_installed).pack(side="right")
        ttk.Button(top, text="brew update", command=lambda: self.run_brew([["update"]])).pack(side="right", padx=6)

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True)
        pkg_tab = ttk.Frame(self.notebook)
        self.notebook.add(pkg_tab, text="📦 Packages")
        self.notebook.add(SkillsTab(self.notebook, self), text="🧠 Skills")
        self.notebook.add(McpTab(self.notebook, self), text="🔌 MCP")

        bar = ttk.Frame(pkg_tab, padding=(10, 0, 10, 8))
        bar.pack(fill="x")
        ttk.Label(bar, text="Profile:").pack(side="left")
        for label, _ in PROFILES:
            ttk.Radiobutton(bar, text=label, value=label, variable=self.profile,
                            command=self._on_profile).pack(side="left", padx=4)
        ttk.Label(bar, text="  Platform:").pack(side="left")
        plat = ttk.Combobox(bar, textvariable=self.platform, values=[cd.MAC, cd.LINUX],
                            width=7, state="readonly")
        plat.pack(side="left", padx=4)
        plat.bind("<<ComboboxSelected>>", lambda _e: self._on_profile())
        ttk.Entry(bar, textvariable=self.search, width=34).pack(side="right")
        ttk.Label(bar, text="🔎 Search:").pack(side="right", padx=4)

        paned = ttk.PanedWindow(pkg_tab, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=10)

        # categorias
        left = ttk.Frame(paned)
        self.cat_list = tk.Listbox(left, exportselection=False, width=26, activestyle="none",
                                   borderwidth=0, highlightthickness=1)
        self.cat_list.pack(fill="both", expand=True)
        self.cat_list.bind("<<ListboxSelect>>", self._on_category)
        paned.add(left, weight=1)

        # tabela
        mid = ttk.Frame(paned)
        cols = ("st", "name", "kind", "cat", "desc")
        self.tree = ttk.Treeview(mid, columns=cols, show="headings", selectmode="browse")
        for col, text, w in [("st", "", 34), ("name", "Package", 170), ("kind", "Type", 60),
                             ("cat", "Category", 150), ("desc", "Description", 420)]:
            self.tree.heading(col, text=text)
            self.tree.column(col, width=w, anchor="w", stretch=(col == "desc"))
        self.tree.column("st", anchor="center")
        sb = ttk.Scrollbar(mid, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree.tag_configure("installed", foreground="#2e7d32")
        self.tree.bind("<<TreeviewSelect>>", self._on_select)
        self.tree.bind("<Double-1>", lambda _e: self.toggle_cart())
        paned.add(mid, weight=4)

        # detalhes
        right = ttk.Frame(paned, padding=(10, 0))
        self.d_name = ttk.Label(right, text="Select a package", style="Title.TLabel", wraplength=280)
        self.d_name.pack(anchor="w")
        self.d_meta = ttk.Label(right, style="Sub.TLabel", wraplength=280)
        self.d_meta.pack(anchor="w", pady=(0, 8))
        self.d_desc = ttk.Label(right, wraplength=280, justify="left")
        self.d_desc.pack(anchor="w", pady=(0, 8))
        self.d_url = tk.Label(right, text="", fg="#4a90e2", cursor="pointinghand", wraplength=280,
                              justify="left", anchor="w", background=self.cget("background"))
        self.d_url.pack(anchor="w", pady=(0, 8))
        self.d_url.bind("<Button-1>", lambda _e: self.open_home())
        self.d_reason = ttk.Label(right, wraplength=280, justify="left", foreground="#1565c0")
        self.d_reason.pack(anchor="w", pady=(0, 8))
        self.d_cmd = tk.Text(right, height=3, width=34, wrap="word", relief="flat",
                             background=self.cget("background"), state="disabled")
        self.d_cmd.pack(fill="x", pady=(0, 8))
        self.btn_install = ttk.Button(right, text="Install", command=self.install_selected)
        self.btn_remove = ttk.Button(right, text="Uninstall", command=self.uninstall_selected)
        self.btn_cart = ttk.Button(right, text="Add to list", command=self.toggle_cart)
        self.btn_copy = ttk.Button(right, text="Copy command", command=self.copy_cmd)
        self.btn_home = ttk.Button(right, text="Open page", command=self.open_home)
        for b in (self.btn_install, self.btn_remove, self.btn_cart, self.btn_copy, self.btn_home):
            b.pack(fill="x", pady=2)
        ttk.Separator(right).pack(fill="x", pady=8)
        self.cart_lbl = ttk.Label(right, text="List: 0 items")
        self.cart_lbl.pack(anchor="w")
        ttk.Button(right, text="Install list", command=self.install_cart).pack(fill="x", pady=2)
        ttk.Button(right, text="Export Brewfile…", command=self.export_brewfile).pack(fill="x", pady=2)
        ttk.Button(right, text="Clear list", command=self.clear_cart).pack(fill="x", pady=2)
        paned.add(right, weight=1)

        # log
        bottom = ttk.Frame(self, padding=10)
        bottom.pack(fill="x", side="bottom")
        self.progress = ttk.Progressbar(bottom, mode="indeterminate")
        self.progress.pack(fill="x", pady=(0, 4))
        self.log = tk.Text(bottom, height=7, state="disabled", wrap="none", background="#1e1e1e",
                           foreground="#d4d4d4", insertbackground="white")
        self.log.pack(fill="x")

        self._fill_categories()

    def _visible_profile(self) -> Optional[str]:
        return dict(PROFILES)[self.profile.get()]

    def _fill_categories(self) -> None:
        prof = self._visible_profile()
        cats = cd.ALL_CATEGORIES
        if prof == cd.DEV:
            cats = cd.CATEGORIES_DEV
        elif prof == cd.GAMER:
            cats = cd.CATEGORIES_GAMER
        self.cat_entries = [ALL, SUGGEST, KITS, CART] + list(cats)
        self.cat_list.delete(0, "end")
        for c in self.cat_entries:
            self.cat_list.insert("end", c)
        idx = self.cat_entries.index(self.category) if self.category in self.cat_entries else 0
        self.category = self.cat_entries[idx]
        self.cat_list.selection_set(idx)

    def _on_profile(self) -> None:
        self._fill_categories()
        self.refresh()

    def _on_category(self, _e=None) -> None:
        sel = self.cat_list.curselection()
        if sel:
            self.category = self.cat_entries[sel[0]]
            self.refresh()

    # ───────────────────────── dados ─────────────────────────
    def is_installed(self, item: cd.Item) -> bool:
        return item.name in self.installed[item.kind]

    def _matches(self, item: cd.Item) -> bool:
        prof = self._visible_profile()
        if prof and prof not in item.profiles:
            return False
        if self.platform.get() not in item.platforms:
            return False
        q = self.search.get().strip().lower()
        if q:
            hay = " ".join((item.name, item.desc, item.category, *item.tags)).lower()
            return all(w in hay for w in q.split())
        return True

    def suggestions(self) -> List[Tuple[cd.Item, str]]:
        """Score uninstalled items by tag overlap with what you already have."""
        have = [i for i in cd.ITEMS if self.is_installed(i)]
        weights: Dict[str, int] = {}
        for i in have:
            for t in i.tags:
                weights[t] = weights.get(t, 0) + 1
        prof = self._visible_profile()
        out: List[Tuple[int, cd.Item, str]] = []
        for item in cd.ITEMS:
            if self.is_installed(item) or not self._matches(item):
                continue
            shared = [t for t in item.tags if t in weights]
            score = sum(weights[t] for t in shared)
            reason = ""
            if shared:
                srcs = [h.name for h in have if set(h.tags) & set(shared)][:3]
                reason = f"Pairs well with what you use: {', '.join(srcs)}"
            if item.key in sum((cd.ESSENTIALS[p] for p in ([prof] if prof else cd.ESSENTIALS)), []):
                score += 3
                reason = reason or "Essential for this profile"
            if score:
                out.append((score, item, reason))
        out.sort(key=lambda t: (-t[0], t[1].name))
        return [(i, r) for _, i, r in out[:40]]

    def refresh(self) -> None:
        self.tree.delete(*self.tree.get_children())
        self.rows.clear()
        self.reasons.clear()
        cat = self.category
        q = self.search.get().strip().lower()

        if cat == KITS:
            self.tree.heading("kind", text="Items")
            prof = self._visible_profile()
            for kit in cd.KITS:
                if prof and kit.profile != prof:
                    continue
                if q and q not in (kit.name + kit.desc).lower():
                    continue
                items = [cd.BY_KEY[k] for k in kit.keys]
                done = sum(self.is_installed(i) for i in items)
                iid = self.tree.insert("", "end", values=(
                    "✓" if done == len(items) else "", kit.name, f"{done}/{len(items)}",
                    "Kit " + kit.profile, kit.desc))
                self.rows[iid] = kit
            self._after_refresh()
            return

        self.tree.heading("kind", text="Type")
        if cat == SUGGEST:
            pairs = self.suggestions()
        elif cat == CART:
            pairs = [(cd.BY_KEY[k], "") for k in sorted(self.cart)
                     if self._matches(cd.BY_KEY[k])]
        else:
            pairs = [(i, "") for i in sorted(cd.ITEMS, key=lambda x: x.name)
                     if (cat == ALL or i.category == cat) and self._matches(i)]
        for item, reason in pairs:
            mark = "✓" if self.is_installed(item) else ("🛒" if item.key in self.cart else "")
            iid = self.tree.insert("", "end", values=(mark, item.name, item.kind, item.category, item.desc),
                                   tags=("installed",) if mark == "✓" else ())
            self.rows[iid] = item
            self.reasons[iid] = reason
        self._after_refresh()

    def _after_refresh(self) -> None:
        self.cart_lbl.config(text=f"List: {len(self.cart)} items")
        self._on_select()

    # ───────────────────────── detalhes ─────────────────────────
    def selected(self):
        sel = self.tree.selection()
        return (self.rows.get(sel[0]), sel[0]) if sel else (None, None)

    def _set_cmd(self, text: str) -> None:
        self.d_cmd.config(state="normal")
        self.d_cmd.delete("1.0", "end")
        self.d_cmd.insert("1.0", text)
        self.d_cmd.config(state="disabled")

    def _on_select(self, _e=None) -> None:
        obj, iid = self.selected()
        if obj is None:
            self.d_name.config(text="Select a package")
            for w in (self.d_meta, self.d_desc, self.d_reason, self.d_url):
                w.config(text="")
            self._set_cmd("")
            self._sync_buttons(None)
            return
        if isinstance(obj, cd.Kit):
            items = [cd.BY_KEY[k] for k in obj.keys]
            self.d_name.config(text=obj.name)
            self.d_meta.config(text=f"Kit • {obj.profile} • {len(items)} pacotes")
            self.d_desc.config(text=obj.desc + "\n\n" + "\n".join(
                f"{'✓' if self.is_installed(i) else '•'} {i.name} ({i.kind})" for i in items))
            self.d_reason.config(text="")
            self.d_url.config(text="")
            self._set_cmd(self.kit_commands_text(obj))
        else:
            self.d_name.config(text=obj.name)
            self.d_meta.config(text=f"{obj.kind} • {obj.category} • "
                                    f"{'/'.join(obj.platforms)}"
                                    f"{' • installed' if self.is_installed(obj) else ''}")
            self.d_desc.config(text=obj.desc)
            self.d_reason.config(text=self.reasons.get(iid, ""))
            self.d_url.config(text="🔗 " + self.page_url(obj))
            self._set_cmd("brew " + " ".join(obj.install_cmd))
        self._sync_buttons(obj)

    def _sync_buttons(self, obj) -> None:
        can = self.brew is not None and not self.busy
        st = lambda ok: "normal" if ok else "disabled"
        if obj is None:
            for b in (self.btn_install, self.btn_remove, self.btn_cart, self.btn_copy, self.btn_home):
                b.config(state="disabled")
            return
        is_kit = isinstance(obj, cd.Kit)
        self.btn_install.config(text="Install kit" if is_kit else "Install", state=st(can))
        self.btn_remove.config(state=st(can and not is_kit and self.is_installed(obj)))
        self.btn_cart.config(text="Add kit to list" if is_kit else (
            "Remove from list" if obj.key in self.cart else "Add to list"), state="normal")
        self.btn_copy.config(state="normal")
        self.btn_home.config(state=st(can and not is_kit))

    def kit_items(self, kit: cd.Kit) -> List[cd.Item]:
        return [cd.BY_KEY[k] for k in kit.keys if self.platform.get() in cd.BY_KEY[k].platforms]

    def kit_commands_text(self, kit: cd.Kit) -> str:
        return "\n".join("brew " + " ".join(i.install_cmd) for i in self.kit_items(kit)
                         if not self.is_installed(i))

    # ───────────────────────── actions ─────────────────────────
    def toggle_cart(self) -> None:
        obj, _ = self.selected()
        if obj is None:
            return
        keys = obj.keys if isinstance(obj, cd.Kit) else (obj.key,)
        if isinstance(obj, cd.Kit):
            self.cart.update(k for k in keys if self.platform.get() in cd.BY_KEY[k].platforms)
        elif obj.key in self.cart:
            self.cart.discard(obj.key)
        else:
            self.cart.add(obj.key)
        self.refresh()

    def clear_cart(self) -> None:
        self.cart.clear()
        self.refresh()

    def copy_cmd(self) -> None:
        obj, _ = self.selected()
        if obj is None:
            return
        text = self.kit_commands_text(obj) if isinstance(obj, cd.Kit) else "brew " + " ".join(obj.install_cmd)
        self.clipboard_clear()
        self.clipboard_append(text)
        self._log("info", "Command copied to clipboard.\n")

    @staticmethod
    def page_url(item: cd.Item) -> str:
        return f"https://formulae.brew.sh/{item.kind}/{item.name}"

    def open_home(self) -> None:
        obj, _ = self.selected()
        if isinstance(obj, cd.Item):
            webbrowser.open(self.page_url(obj))

    def install_selected(self) -> None:
        obj, _ = self.selected()
        if isinstance(obj, cd.Kit):
            cmds = [i.install_cmd for i in self.kit_items(obj) if not self.is_installed(i)]
        elif obj is not None:
            cmds = [obj.install_cmd]
        else:
            return
        if cmds:
            self.run_brew(cmds)
        else:
            self._log("info", "Everything in this kit is already installed.\n")

    def uninstall_selected(self) -> None:
        obj, _ = self.selected()
        if isinstance(obj, cd.Item) and messagebox.askyesno("Uninstall", f"Uninstall {obj.name}?"):
            cmd = ["uninstall"] + (["--cask"] if obj.kind == "cask" else []) + [obj.name]
            self.run_brew([cmd])

    def install_cart(self) -> None:
        items = [cd.BY_KEY[k] for k in sorted(self.cart)
                 if not self.is_installed(cd.BY_KEY[k]) and self.platform.get() in cd.BY_KEY[k].platforms]
        if not items:
            messagebox.showinfo("My list", "Nothing to install in the list.")
            return
        if messagebox.askyesno("Install list", f"Install {len(items)} packages?\n\n"
                               + ", ".join(i.name for i in items)):
            self.run_brew([i.install_cmd for i in items])

    def export_brewfile(self) -> None:
        obj, _ = self.selected()
        keys = set(self.cart)
        if not keys and obj is not None:
            keys = set(obj.keys) if isinstance(obj, cd.Kit) else {obj.key}
        if not keys:
            messagebox.showinfo("Brewfile", "Add items to the list (double-click) or select a kit.")
            return
        path = filedialog.asksaveasfilename(initialfile="Brewfile", title="Save Brewfile")
        if not path:
            return
        lines = [f'{cd.BY_KEY[k].kind == "cask" and "cask" or "brew"} "{cd.BY_KEY[k].name}"'
                 for k in sorted(keys) if self.platform.get() in cd.BY_KEY[k].platforms]
        with open(path, "w") as fh:
            fh.write("\n".join(lines) + "\n")
        self._log("info", f"Brewfile saved to {path}  (use: brew bundle --file={path})\n")

    # ───────────────────────── brew ─────────────────────────
    def _log(self, tag: str, text: object) -> None:
        self.log.config(state="normal")
        self.log.insert("end", text)
        self.log.see("end")
        self.log.config(state="disabled")

    def _poll_log(self) -> None:
        try:
            while True:
                tag, text = self.log_q.get_nowait()
                if tag == "done":
                    self._finish()
                elif tag == "call":
                    text()  # type: ignore[operator]
                elif tag == "installed":
                    self._set_installed(text)  # type: ignore[arg-type]
                else:
                    self._log(tag, text)
        except queue.Empty:
            pass
        self.after(100, self._poll_log)

    def _finish(self) -> None:
        self.busy = False
        self.progress.stop()
        self.refresh_installed()

    def run_brew(self, cmds: List[List[str]]) -> None:
        if not self.brew:
            messagebox.showerror("Homebrew", "brew not found. Install it from https://brew.sh")
            return
        if self.busy:
            return
        self.busy = True
        self.progress.start(12)
        self._on_select()
        env = dict(os.environ, HOMEBREW_NO_ANALYTICS="1", HOMEBREW_NO_COLOR="1",
                   HOMEBREW_NO_ENV_HINTS="1", NONINTERACTIVE="1")

        def worker() -> None:
            for args in cmds:
                self.log_q.put(("cmd", f"\n$ brew {' '.join(args)}\n"))
                try:
                    p = subprocess.Popen([self.brew, *args], stdout=subprocess.PIPE,
                                         stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                         text=True, env=env)
                    for line in p.stdout:  # type: ignore[union-attr]
                        self.log_q.put(("out", line))
                    p.wait()
                    self.log_q.put(("info", f"→ exit code {p.returncode}\n"))
                except OSError as exc:
                    self.log_q.put(("err", f"Error: {exc}\n"))
            self.log_q.put(("done", ""))

        threading.Thread(target=worker, daemon=True).start()

    def refresh_installed(self) -> None:
        if not self.brew:
            self.refresh()
            return

        def worker() -> None:
            res = {}
            for kind in ("formula", "cask"):
                try:
                    out = subprocess.run([self.brew, "list", f"--{kind}", "-1"], capture_output=True,
                                         text=True, timeout=60).stdout
                    res[kind] = set(out.split())
                except (OSError, subprocess.SubprocessError):
                    res[kind] = set()
            self.log_q.put(("installed", res))

        threading.Thread(target=worker, daemon=True).start()

    def _set_installed(self, res: Dict[str, Set[str]]) -> None:
        self.installed = res
        self.refresh()


if __name__ == "__main__":
    App().mainloop()
