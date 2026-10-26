#!/usr/bin/env python3
"""brewcat: visual package catalog for devs and gamers (macOS and Linux)."""
from __future__ import annotations

import os
import platform
import queue
import re
import shutil
import subprocess
import sys
import threading
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, ttk
from typing import Dict, List, Optional, Set, Tuple

import catalog_data as cd
from help_text import HELP, VERSION, os_description
from extras_tab import McpTab, SkillsTab
from logo import draw_canvas as draw_logo

os.environ.setdefault("TK_SILENCE_DEPRECATION", "1")

if any(a in ("-h", "--help", "help") for a in sys.argv[1:]):
    print(HELP)
    sys.exit(0)
if any(a in ("-V", "--version") for a in sys.argv[1:]):
    print(f"brewcat {VERSION}\n{os_description()}")
    sys.exit(0)


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


def _ensure_branded_launcher() -> None:
    """macOS shows the process name in the menu bar and Dock ("Python"). Re-launch through a tiny
    brewcat.app (a copy of Python's launcher stub) so it shows "brewcat" and the cat icon."""
    if sys.platform != "darwin" or os.environ.get("BREWCAT_BRANDED"):
        return
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        stub = os.path.join(sys.base_prefix, "Resources/Python.app/Contents/MacOS/Python")
        if not os.path.exists(stub):
            return
        base = os.path.expanduser("~/Library/Application Support/brewcat/brewcat.app")
        exe = os.path.join(base, "Contents/MacOS/brewcat")
        marker = os.path.join(base, "Contents/.stub")
        want = os.path.realpath(stub)
        if not (os.path.exists(exe) and os.path.exists(marker) and open(marker).read() == want):
            shutil.rmtree(base, ignore_errors=True)
            os.makedirs(os.path.dirname(exe))
            os.makedirs(os.path.join(base, "Contents/Resources"))
            shutil.copy2(stub, exe)
            for icns in (os.path.join(here, "assets/brewcat.icns"), os.path.join(here, "brewcat.icns")):
                if os.path.exists(icns):
                    shutil.copy2(icns, os.path.join(base, "Contents/Resources/brewcat.icns"))
                    break
            with open(os.path.join(base, "Contents/Info.plist"), "w") as fh:
                fh.write("""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleName</key><string>brewcat</string>
<key>CFBundleDisplayName</key><string>brewcat</string>
<key>CFBundleIdentifier</key><string>com.github.1985epma.brewcat</string>
<key>CFBundleExecutable</key><string>brewcat</string>
<key>CFBundleIconFile</key><string>brewcat</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>NSHighResolutionCapable</key><true/>
</dict></plist>
""")
            with open(marker, "w") as fh:
                fh.write(want)
        os.environ["BREWCAT_BRANDED"] = "1"
        os.execv(exe, [exe, os.path.join(here, "app.py"), *sys.argv[1:]])
    except Exception:  # noqa: BLE001 - branding is cosmetic; never block startup
        os.environ["BREWCAT_BRANDED"] = "1"


_ensure_branded_launcher()

SYSTEM = cd.MAC if platform.system() == "Darwin" else cd.LINUX
BREW_CANDIDATES = [
    "/opt/homebrew/bin/brew",
    "/usr/local/bin/brew",
    "/home/linuxbrew/.linuxbrew/bin/brew",
    os.path.expanduser("~/.linuxbrew/bin/brew"),
]

ALL, SUGGEST, KITS, CART = "★ All", "✨ Suggestions", "📦 Kits", "🛒 My list"
SEARCH = "🔎 Homebrew search"
EXTRA_CAT = "Homebrew search"
PROFILES = [("All", None), ("Dev", cd.DEV), ("SRE / Cloud", cd.SRE), ("QA", cd.QA),
            ("Data Scientist", cd.DS), ("Data Engineer", cd.DE), ("Support & Network", cd.NET),
            ("Security", cd.SEC), ("Design (web, video, graphics)", cd.DESIGN), ("DJ / Music", cd.DJ),
            ("Office", cd.OFFICE), ("Vendors (Microsoft, Oracle, Apple, Open Source, Red Hat, JetBrains)", cd.VENDOR),
            ("Gamer", cd.GAMER)]


def find_brew() -> Optional[str]:
    return shutil.which("brew") or next((p for p in BREW_CANDIDATES if os.path.exists(p)), None)


def ensure_askpass() -> Optional[str]:
    """Create a SUDO_ASKPASS helper. brew runs without a terminal, so casks that need `sudo`
    (Microsoft Office, drivers, pkg installers…) would hang; with this helper sudo asks for the
    password in a native dialog instead."""
    base = os.path.expanduser("~/Library/Application Support/brewcat" if sys.platform == "darwin"
                              else "~/.local/share/brewcat")
    path = os.path.join(base, "askpass.sh")
    if sys.platform == "darwin":
        body = ("#!/bin/bash\n"
                "/usr/bin/osascript -e 'text returned of (display dialog "
                "\"brewcat: enter your macOS password to continue the installation\" "
                "default answer \"\" with hidden answer with icon caution with title \"brewcat\")'\n")
    else:
        body = ("#!/bin/bash\n"
                "if command -v zenity >/dev/null; then exec zenity --password --title=brewcat\n"
                "elif command -v kdialog >/dev/null; then exec kdialog --password 'brewcat: enter your password'\n"
                "else exit 1; fi\n")
    try:
        os.makedirs(base, exist_ok=True)
        if not os.path.exists(path) or open(path).read() != body:
            with open(path, "w") as fh:
                fh.write(body)
        os.chmod(path, 0o700)
        return path
    except OSError:
        return None


def apple_silicon() -> bool:
    """True on Apple Silicon hardware, even when this process runs translated under Rosetta."""
    if sys.platform != "darwin":
        return False
    if platform.machine() == "arm64":
        return True
    try:
        return subprocess.run(["/usr/sbin/sysctl", "-n", "hw.optional.arm64"], capture_output=True,
                              text=True, timeout=5).stdout.strip() == "1"
    except (OSError, subprocess.SubprocessError):
        return False


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
        self.extra: List[cd.Item] = []  # results of `brew search` outside the curated catalog
        self.extra_desc: Dict[str, str] = {}
        self._search_job: Optional[str] = None

        self.profile = tk.StringVar(value="All")
        self.platform = tk.StringVar(value=SYSTEM)
        self.search = tk.StringVar()
        self.category = ALL

        self._build_ui()
        self.search.trace_add("write", self._on_search_change)
        self.after(100, self._poll_log)
        self.createcommand("tk::mac::ShowAbout", self.show_about)  # macOS app menu > About brewcat
        self.refresh_installed()
        self.after(1500, self._check_rosetta)

    # ───────────────────────── UI ─────────────────────────
    def _build_ui(self) -> None:
        style = ttk.Style(self)
        style.configure("Title.TLabel", font=("TkDefaultFont", 16, "bold"))
        style.configure("Sub.TLabel", foreground="#666666")
        style.configure("Treeview", rowheight=24)

        top = ttk.Frame(self, padding=(10, 8))
        top.pack(fill="x")
        logo = tk.Canvas(top, width=36, height=36, highlightthickness=0, bd=0)
        draw_logo(logo, 36)
        logo.pack(side="left", padx=(0, 8))
        ttk.Label(top, text="brewcat", style="Title.TLabel").pack(side="left")
        ttk.Label(top, text=f"  {'macOS' if SYSTEM == cd.MAC else 'Linux'}"
                            f" • {'brew found' if self.brew else 'brew NOT found'}",
                  style="Sub.TLabel").pack(side="left")
        ttk.Button(top, text="About", command=self.show_about).pack(side="right", padx=(6, 0))
        ttk.Button(top, text="Help", command=self.show_help).pack(side="right", padx=(6, 0))
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
        prof_box = ttk.Combobox(bar, textvariable=self.profile, values=[p for p, _ in PROFILES],
                                width=28, state="readonly")
        prof_box.pack(side="left", padx=4)
        prof_box.bind("<<ComboboxSelected>>", lambda _e: self._on_profile())
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
        cats = cd.PROFILE_CATEGORIES.get(prof, cd.ALL_CATEGORIES) if prof else cd.ALL_CATEGORIES
        self.cat_entries = [ALL, SUGGEST, KITS, CART, SEARCH] + list(cats)
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

    def show_about(self) -> None:
        win = tk.Toplevel(self)
        win.title("About brewcat")
        win.resizable(False, False)
        body = ttk.Frame(win, padding=20)
        body.pack()
        logo = tk.Canvas(body, width=96, height=96, highlightthickness=0, bd=0)
        draw_logo(logo, 96)
        logo.grid(row=0, column=0, rowspan=2, padx=(0, 16))
        ttk.Label(body, text="brewcat", style="Title.TLabel").grid(row=0, column=1, sticky="sw")
        ttk.Label(body, text=f"Version {VERSION}").grid(row=1, column=1, sticky="nw")
        info = ttk.Frame(body)
        info.grid(row=2, column=0, columnspan=2, sticky="w", pady=(14, 0))
        rows = [("OS", os_description()),
                ("Python", f"{platform.python_version()} (Tk {tk.TkVersion:g})"),
                ("Homebrew", "checking…"),
                ("License", "MIT"),
                ("Source", "github.com/1985epma/homebrew-brewcat")]
        values = {}
        for i, (k, v) in enumerate(rows):
            ttk.Label(info, text=k + ":", style="Sub.TLabel").grid(row=i, column=0, sticky="nw", padx=(0, 10))
            values[k] = ttk.Label(info, text=v, wraplength=360, justify="left")
            values[k].grid(row=i, column=1, sticky="w")
        ttk.Button(body, text="OK", command=win.destroy).grid(row=3, column=0, columnspan=2, pady=(16, 0))

        def worker() -> None:
            try:
                out = subprocess.run(self.brew_cmd("--version"), capture_output=True, text=True,
                                     timeout=15).stdout.split("\n")[0] if self.brew else "not found"
            except (OSError, subprocess.SubprocessError):
                out = "unavailable"
            self.log_q.put(("call", lambda: values["Homebrew"].winfo_exists() and
                            values["Homebrew"].config(text=out or "unavailable")))

        threading.Thread(target=worker, daemon=True).start()

    def show_help(self) -> None:
        win = tk.Toplevel(self)
        win.title("brewcat Help")
        win.geometry("820x640")
        txt = tk.Text(win, wrap="word", padx=14, pady=10, font=("Menlo", 12) if SYSTEM == cd.MAC else "TkFixedFont")
        sb = ttk.Scrollbar(win, orient="vertical", command=txt.yview)
        txt.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        txt.pack(fill="both", expand=True)
        txt.insert("1.0", HELP)
        txt.config(state="disabled")
        self.bind_all("<F1>", lambda _e: self.show_help())

    def brew_cmd(self, *args: str) -> List[str]:
        """Run brew in the architecture of its prefix. If this app is launched under Rosetta, a plain
        `brew` in /opt/homebrew fails with "Cannot install under Rosetta 2 in ARM default prefix"."""
        if args and args[0] in ("install", "uninstall", "reinstall"):
            # Package names come after "--" so a name can never be parsed as a brew option.
            opts = [a for a in args[1:] if a.startswith("-")]
            names = [a for a in args[1:] if not a.startswith("-")]
            args = (args[0], *opts, "--", *names)
        if apple_silicon() and os.path.exists("/usr/bin/arch"):
            if self.brew.startswith("/opt/homebrew"):
                return ["/usr/bin/arch", "-arm64", self.brew, *args]
            if self.brew.startswith("/usr/local"):
                return ["/usr/bin/arch", "-x86_64", self.brew, *args]
        return [self.brew, *args]

    # ───────────────────── Rosetta 2 (Apple Silicon) ─────────────────────
    @staticmethod
    def rosetta_missing() -> bool:
        return (apple_silicon()
                and not os.path.exists("/Library/Apple/usr/share/rosetta/rosetta"))

    def _check_rosetta(self) -> None:
        """Many casks are Intel-only; without Rosetta 2 macOS shows an install prompt/error."""
        flag = os.path.expanduser("~/Library/Application Support/brewcat/rosetta_declined")
        if not self.rosetta_missing() or os.path.exists(flag):
            return
        if messagebox.askyesno("Install Rosetta 2?",
                               "Rosetta 2 is not installed on this Apple Silicon Mac.\n\n"
                               "Many apps (especially casks) are Intel-only and need it, otherwise macOS "
                               "shows an error asking to install it.\n\n"
                               "Install Rosetta 2 now? macOS will ask for your administrator password."):
            self.install_rosetta()
        else:
            os.makedirs(os.path.dirname(flag), exist_ok=True)
            open(flag, "w").close()
            self._log("info", "Rosetta 2 skipped. Install later with: "
                              "softwareupdate --install-rosetta --agree-to-license\n")

    def install_rosetta(self) -> None:
        self._log("cmd", "\n$ softwareupdate --install-rosetta --agree-to-license  (administrator)\n")
        self.busy = True
        self.progress.start(12)

        def worker() -> None:
            script = 'do shell script "/usr/sbin/softwareupdate --install-rosetta --agree-to-license" ' \
                     'with administrator privileges'
            try:
                r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=900)
                self.log_q.put(("out", (r.stdout + r.stderr).strip() + "\n"))
                ok = r.returncode == 0
            except (OSError, subprocess.SubprocessError) as exc:
                self.log_q.put(("err", f"Error: {exc}\n"))
                ok = False
            self.log_q.put(("info", "✓ Rosetta 2 installed.\n" if ok else "✗ Rosetta 2 was not installed.\n"))
            self.log_q.put(("done", ""))

        threading.Thread(target=worker, daemon=True).start()

    # ───────────────────── search by name in all of Homebrew ─────────────────────
    def _on_search_change(self, *_args) -> None:
        self.refresh()
        if self._search_job:
            self.after_cancel(self._search_job)
        q = self.search.get().strip()
        if len(q) < 2 or not self.brew:
            self.extra = []
            return
        self._search_job = self.after(400, lambda: self._remote_search(q))

    def _remote_search(self, q: str) -> None:
        words = q.lower().split()

        def worker() -> None:
            found: List[Tuple[str, str]] = []
            for kind, flag in (("formula", "--formulae"), ("cask", "--casks")):
                try:
                    out = subprocess.run(self.brew_cmd("search", flag, words[0]), capture_output=True,
                                         text=True, timeout=30).stdout
                except (OSError, subprocess.SubprocessError):
                    continue
                for name in out.split():
                    short = name.rsplit("/", 1)[-1]
                    if all(w in name.lower() for w in words) and f"{kind}:{short}" not in cd.BY_KEY:
                        found.append((kind, name))
            self.log_q.put(("call", lambda: self._set_extra(q, found)))

        threading.Thread(target=worker, daemon=True).start()

    def _set_extra(self, q: str, found: List[Tuple[str, str]]) -> None:
        if q != self.search.get().strip():
            return  # stale result
        items = []
        for kind, name in sorted(found, key=lambda t: (t[1], t[0]))[:60]:
            if not re.fullmatch(r"[\w][\w.+@/-]*", name):
                continue  # ignore anything that is not a plausible package name
            tap = ""
            if "/" in name:  # tap-qualified result: user/repo/name
                tap, name = name.rsplit("/", 1)
            it = cd.Item(name, kind, EXTRA_CAT, "Not in the curated catalog", (cd.DEV, cd.SRE, cd.GAMER),
                         cd.BOTH if kind == "formula" else (cd.MAC,), ("search",), tap)
            cd.BY_KEY[it.key] = it
            items.append(it)
        self.extra = items
        self.refresh()

    def _fetch_desc(self, item: cd.Item) -> None:
        self.extra_desc[item.key] = ""

        def worker() -> None:
            try:
                out = subprocess.run(self.brew_cmd("desc", f"--{item.kind}", item.full_name),
                                     capture_output=True, text=True, timeout=30).stdout.strip()
            except (OSError, subprocess.SubprocessError):
                out = ""
            text = out.split(":", 1)[1].strip() if ":" in out else (out or "No description available.")
            self.log_q.put(("call", lambda: self._set_desc(item, text)))

        threading.Thread(target=worker, daemon=True).start()

    def _set_desc(self, item: cd.Item, text: str) -> None:
        self.extra_desc[item.key] = text
        obj, _ = self.selected()
        if obj is not None and getattr(obj, "key", None) == item.key:
            self.d_desc.config(text=text)

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
        elif cat == SEARCH:
            pairs = [(i, "") for i in self.extra if self.platform.get() in i.platforms]
        else:
            pairs = [(i, "") for i in sorted(cd.ITEMS, key=lambda x: x.name)
                     if (cat == ALL or i.category == cat or cat in i.groups) and self._matches(i)]
            if cat == ALL:
                pairs += [(i, "") for i in self.extra if self.platform.get() in i.platforms]
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
            desc = obj.desc
            if obj.category == EXTRA_CAT:
                desc = self.extra_desc.get(obj.key) or "Not in the curated catalog. Loading description…"
                if obj.key not in self.extra_desc:
                    self._fetch_desc(obj)
            self.d_desc.config(text=desc)
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
        if item.tap:
            user, repo = item.tap.split("/")
            return f"https://github.com/{user}/homebrew-{repo}"
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
            lines = "\n".join("brew " + " ".join(c) for c in cmds)
            if messagebox.askyesno("Confirm installation", f"Run the following?\n\n{lines}"):
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
        lines = [f'{cd.BY_KEY[k].kind == "cask" and "cask" or "brew"} "{cd.BY_KEY[k].full_name}"'
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
        askpass = ensure_askpass()
        if askpass:
            env["SUDO_ASKPASS"] = askpass

        def worker() -> None:
            for args in cmds:
                self.log_q.put(("cmd", f"\n$ brew {' '.join(args)}\n"))
                try:
                    p = subprocess.Popen(self.brew_cmd(*args), stdout=subprocess.PIPE,
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
                    out = subprocess.run(self.brew_cmd("list", f"--{kind}", "-1"), capture_output=True,
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
