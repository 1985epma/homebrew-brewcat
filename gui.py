"""brewcat window (needs Tk). app.py is the entry point and loads this module only when a window is wanted."""
from __future__ import annotations

import os
import platform
import queue
import re
import subprocess
import sys
import threading
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, ttk
from typing import Dict, List, Optional, Set, Tuple

import catalog_data as cd
from brewenv import apple_silicon, brew_command, find_brew, install_with_retry
from brewrunner import BrewRunner
from help_text import HELP, VERSION, os_description
from extras_tab import McpTab, SkillsTab
from logo import draw_canvas as draw_logo

os.environ.setdefault("TK_SILENCE_DEPRECATION", "1")

def _reexec_with_modern_tk() -> None:
    """The system Python's Tk 8.5 renders a blank window on recent macOS; use Homebrew's python-tk."""
    if tk.TkVersion >= 8.6 or os.environ.get("BREWCAT_REEXEC"):
        return
    for py in ("/opt/homebrew/bin/python3", "/usr/local/bin/python3",
               "/home/linuxbrew/.linuxbrew/bin/python3"):
        real = os.path.realpath(py)
        # Only trust a Python that really lives inside a Homebrew prefix (not an arbitrary file).
        in_brew = real.startswith(("/opt/homebrew/", "/usr/local/Cellar/", "/usr/local/opt/",
                                   "/home/linuxbrew/.linuxbrew/"))
        if os.path.exists(py) and in_brew and real != os.path.realpath(sys.executable):
            os.environ["BREWCAT_REEXEC"] = "1"
            os.execv(py, [py, *sys.argv])
    print("Warning: Tk < 8.6 detected; the window may be blank. Run: brew install python-tk",
          file=sys.stderr)





SYSTEM = cd.MAC if platform.system() == "Darwin" else cd.LINUX

ALL, SUGGEST, KITS, CART = "★ All", "✨ Suggestions", "📦 Kits", "🛒 My list"
SEARCH = "🔎 Homebrew search"
EXTRA_CAT = "Homebrew search"
PROFILES = [("All", None), ("117-labs (by 1985epma)", cd.LABS), ("Dev", cd.DEV), ("SRE / Cloud", cd.SRE), ("QA", cd.QA),
            ("Data Scientist", cd.DS), ("Data Engineer", cd.DE), ("Support & Network", cd.NET),
            ("Security", cd.SEC), ("Design (web, video, graphics)", cd.DESIGN), ("DJ / Music", cd.DJ),
            ("Office", cd.OFFICE), ("Vendors (Microsoft, Oracle, Apple, Open Source, Red Hat, JetBrains)", cd.VENDOR),
            ("Gamer", cd.GAMER)]


def config_dir() -> str:
    """Where brewcat keeps its small per-user files (askpass helper, one-time flags)."""
    return os.path.expanduser("~/Library/Application Support/brewcat" if sys.platform == "darwin"
                              else "~/.local/share/brewcat")


def ensure_askpass() -> Optional[str]:
    """Create a SUDO_ASKPASS helper. brew runs without a terminal, so casks that need `sudo`
    (Microsoft Office, drivers, pkg installers…) would hang; with this helper sudo asks for the
    password in a native dialog instead."""
    base = config_dir()
    path = os.path.join(base, "askpass.sh")
    if sys.platform == "darwin":
        body = ("#!/bin/bash\n"
                "/usr/bin/osascript -e 'on run argv' "
                "-e 'set pkg to item 1 of argv' "
                "-e 'set msg to \"brewcat: enter your macOS password\"' "
                "-e 'if pkg is not \"\" then set msg to msg & \" to install \" & pkg' "
                "-e 'text returned of (display dialog msg default answer \"\" with hidden answer "
                "with icon caution with title \"brewcat\")' "
                "-e 'end run' -- \"${BREWCAT_PKG:-}\"\n")
    else:
        body = ("#!/bin/bash\n"
                "if command -v zenity >/dev/null; then exec zenity --password --title=\"brewcat ${BREWCAT_PKG:-}\"\n"
                "elif command -v kdialog >/dev/null; then exec kdialog --password \"brewcat: enter your password ${BREWCAT_PKG:-}\"\n"
                "else exit 1; fi\n")
    try:
        os.makedirs(base, exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o700)  # never group/world readable
        with os.fdopen(fd, "w") as fh:
            fh.write(body)
        os.chmod(path, 0o700)
        return path
    except OSError:
        return None


class BatchResult:
    """What happened in one batch of brew commands (no tkinter). Fed by the run_one wrapper in App.run_brew with
    the arguments and exit code of every brew call, including the package-by-package retries that
    install_with_retry makes after a failed batch."""

    def __init__(self) -> None:
        self.calls: List[Tuple[List[str], int]] = []

    def record(self, args: List[str], code: int) -> None:
        self.calls.append((list(args), code))

    @staticmethod
    def _names(args: List[str]) -> List[str]:
        return [a for a in args[1:] if not a.startswith("-")]

    @staticmethod
    def _flags(args: List[str]) -> Tuple[str, ...]:
        return tuple(a for a in args[1:] if a.startswith("-"))

    def succeeded(self) -> List[str]:
        """Packages installed by a call that exited 0."""
        out: List[str] = []
        for args, code in self.calls:
            if code == 0 and args and args[0] == "install":
                out.extend(n for n in self._names(args) if n not in out)
        return out

    def _failed_with_flags(self) -> List[Tuple[str, Tuple[str, ...]]]:
        """A package failed when a single-package install exited non-zero (a failed batch of several is retried
        package by package, so the culprits show up as single-package calls)."""
        done = set(self.succeeded())
        out: List[Tuple[str, Tuple[str, ...]]] = []
        for args, code in self.calls:
            names = self._names(args)
            if code != 0 and args and args[0] == "install" and len(names) == 1 and names[0] not in done \
                    and all(names[0] != n for n, _ in out):
                out.append((names[0], self._flags(args)))
        return out

    def failed_installs(self) -> List[str]:
        return [n for n, _ in self._failed_with_flags()]

    def failed_other(self) -> List[str]:
        """Failed commands that are not package installs (e.g. `brew update`); they are reported, not retried."""
        return ["brew " + " ".join(args) for args, code in self.calls
                if code != 0 and args and args[0] != "install"]

    def retry_commands(self) -> List[List[str]]:
        """Install commands for ONLY the failed packages, grouped by flags (so casks stay casks)."""
        groups: Dict[Tuple[str, ...], List[str]] = {}
        for name, flags in self._failed_with_flags():
            groups.setdefault(flags, []).append(name)
        return [["install", *flags, *names] for flags, names in groups.items()]


class _Modal(tk.Toplevel):
    """Small modal window. The only blocking call is App.wait_window(dialog), so tests can drive the buttons
    (accept/cancel/skip/...) directly."""

    def __init__(self, parent: tk.Tk, title: str) -> None:
        super().__init__(parent)
        self.title(title)
        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.bind("<Escape>", lambda _e: self.close())
        self.after(50, self._grab)

    def _grab(self) -> None:
        try:
            if self.winfo_exists():
                self.grab_set()  # fails while the window is not mapped yet (Linux); then it is simply not modal
        except tk.TclError:
            pass

    def close(self) -> None:
        self.destroy()


class ConfirmDialog(_Modal):
    """Confirmation with a scrollable text (the install plan) and Install / Cancel. `result` is True only after Install."""

    def __init__(self, parent: tk.Tk, title: str, text: str, ok_label: str = "Install") -> None:
        super().__init__(parent, title)
        self.result = False
        self.geometry("640x420")
        self.minsize(420, 260)
        body = ttk.Frame(self, padding=10)
        body.pack(fill="both", expand=True)
        buttons = ttk.Frame(body)
        buttons.pack(side="bottom", fill="x", pady=(8, 0))  # packed first so it stays visible when resized
        self.btn_ok = ttk.Button(buttons, text=ok_label, command=self.accept)
        self.btn_cancel = ttk.Button(buttons, text="Cancel", command=self.close)
        self.btn_ok.pack(side="right")
        self.btn_cancel.pack(side="right", padx=6)
        self.text = tk.Text(body, wrap="word", padx=8, pady=6, height=10)
        sb = ttk.Scrollbar(body, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.text.pack(side="left", fill="both", expand=True)
        self.text.insert("1.0", text)
        self.text.config(state="disabled")

    def accept(self) -> None:
        self.result = True
        self.destroy()


class WelcomeDialog(_Modal):
    """First-run welcome. It never installs anything: `choice` is the profile label the user wants to see kits
    for, or None when skipped/closed."""

    def __init__(self, parent: tk.Tk, default: str = "Dev") -> None:
        super().__init__(parent, "Welcome to brewcat")
        self.choice: Optional[str] = None
        self.profile = tk.StringVar(value=default)
        self.resizable(False, False)
        body = ttk.Frame(self, padding=20)
        body.pack()
        ttk.Label(body, text="Welcome to brewcat", style="Title.TLabel").pack(anchor="w")
        ttk.Label(body, wraplength=380, justify="left",
                  text="brewcat is a catalog of Homebrew packages: browse, pick what you need and install it "
                       "in a click. Nothing is installed until you confirm.").pack(anchor="w", pady=(8, 12))
        ttk.Label(body, text="What do you do?").pack(anchor="w")
        self.combo = ttk.Combobox(body, textvariable=self.profile, values=[p for p, _ in PROFILES],
                                  width=34, state="readonly")
        self.combo.pack(anchor="w", pady=(2, 14))
        buttons = ttk.Frame(body)
        buttons.pack(fill="x")
        self.btn_show = ttk.Button(buttons, text="Show me a starter kit", command=self.show_kit)
        self.btn_skip = ttk.Button(buttons, text="Skip", command=self.skip)
        self.btn_show.pack(side="right")
        self.btn_skip.pack(side="right", padx=6)

    def show_kit(self) -> None:
        self.choice = self.profile.get()
        self.destroy()

    def skip(self) -> None:
        self.choice = None
        self.destroy()


class App(tk.Tk):
    def _set_window_icon(self) -> None:
        """Window and taskbar icon on Linux (on macOS the icon comes from the app bundle)."""
        if sys.platform == "darwin":
            return
        try:
            self._icon = tk.PhotoImage(file=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                         "assets", "brewcat.png"))
            self.iconphoto(True, self._icon)
        except tk.TclError:
            pass  # cosmetic only

    def __init__(self) -> None:
        super().__init__()
        self.title("brewcat")
        self.geometry("1180x720")
        self.minsize(960, 600)
        self._set_window_icon()

        self.brew = find_brew()
        self.installed: Dict[str, Set[str]] = {"formula": set(), "cask": set()}
        self.cart: Set[str] = set()
        self.busy = False
        self.runner = BrewRunner()  # the brew child of the current batch; stopped when the window is closed
        self.log_q: "queue.Queue[Tuple[str, object]]" = queue.Queue()
        self.rows: Dict[str, object] = {}  # iid -> Item | Kit
        self.reasons: Dict[str, str] = {}
        self.extra: List[cd.Item] = []  # results of `brew search` outside the curated catalog
        self.extra_desc: Dict[str, str] = {}
        self._search_job: Optional[str] = None
        self._planning = False  # True while the install plan is being computed in a worker thread
        self.failed_cmds: List[List[str]] = []  # install commands for the packages that failed in the last batch
        self.status_var = tk.StringVar(value="")

        self.profile = tk.StringVar(value="All")
        self.platform = tk.StringVar(value=SYSTEM)
        self.search = tk.StringVar()
        self.category = ALL

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.search.trace_add("write", self._on_search_change)
        self.after(100, self._poll_log)
        self.createcommand("tk::mac::ShowAbout", self.show_about)  # macOS app menu > About brewcat
        self.refresh_installed()
        self.after(1500, self._startup_dialogs)

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
        link_cursor = "pointinghand" if sys.platform == "darwin" else "hand2"  # "pointinghand" is macOS-only
        self.d_url = tk.Label(right, text="", fg="#4a90e2", cursor=link_cursor, wraplength=280,
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
        tools = ttk.Frame(bottom)
        tools.pack(fill="x", pady=(0, 4))
        ttk.Label(tools, textvariable=self.status_var).pack(side="left")
        self.btn_copy_log = ttk.Button(tools, text="Copy log", command=self.copy_log)
        self.btn_retry = ttk.Button(tools, text="Retry failed", command=self.retry_failed, state="disabled")
        self.btn_copy_log.pack(side="right")
        self.btn_retry.pack(side="right", padx=6)
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
                                     timeout=15, check=False).stdout.split("\n")[0] if self.brew else "not found"
            except (OSError, subprocess.SubprocessError):
                out = "unavailable"
            self.log_q.put(("call", lambda: values["Homebrew"].winfo_exists() and
                            values["Homebrew"].config(text=out or "unavailable")))

        threading.Thread(target=worker, daemon=True).start()

    def show_help(self) -> None:
        win = tk.Toplevel(self)
        win.title("brewcat Help")
        win.geometry("820x640")
        tools = ttk.Frame(win, padding=(10, 6))
        tools.pack(side="top", fill="x")
        ttk.Button(tools, text="Copy diagnostics", command=self.copy_diagnostics).pack(side="left")
        ttk.Label(tools, text="  Copies a redacted report to paste into a GitHub issue.",
                  style="Sub.TLabel").pack(side="left")
        txt = tk.Text(win, wrap="word", padx=14, pady=10, font=("Menlo", 12) if SYSTEM == cd.MAC else "TkFixedFont")
        sb = ttk.Scrollbar(win, orient="vertical", command=txt.yview)
        txt.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        txt.pack(fill="both", expand=True)
        txt.insert("1.0", HELP)
        txt.config(state="disabled")
        self.bind_all("<F1>", lambda _e: self.show_help())

    def copy_diagnostics(self) -> None:
        """Copy the redacted diagnostic report (same text as the command line) to the clipboard."""
        try:
            import cli  # lazy: keeps the window import light; cli itself needs no tkinter
            report = getattr(cli, "diagnostic_report")()  # AttributeError if this version has none
        except (AttributeError, ImportError):
            messagebox.showinfo("Diagnostics", "The diagnostic report is not available in this version.")
            return
        except Exception as exc:  # noqa: BLE001 - a diagnostics bug must not crash the window
            messagebox.showerror("Diagnostics", f"Could not build the report: {exc}")
            return
        self.clipboard_clear()
        self.clipboard_append(report)
        messagebox.showinfo("Diagnostics", "Copied. Paste it in your issue.")

    def brew_cmd(self, *args: str) -> List[str]:
        if self.brew is None:
            raise RuntimeError("brew not found")  # callers check self.brew first
        return brew_command(self.brew, *args)

    def _on_close(self) -> None:
        """Closing the window must not leave a brew child running unnoticed in the background."""
        if self.busy and not messagebox.askyesno("Quit brewcat", "An installation is still running. "
                                                                 "Quit and stop it?"):
            return
        self.runner.terminate()
        self.destroy()

    # ───────────────────── first run ─────────────────────
    @staticmethod
    def welcome_flag() -> str:
        return os.path.join(config_dir(), "welcome_seen")

    def _startup_dialogs(self) -> None:
        """One dialog at a time: the welcome (first launch only), then the Rosetta question."""
        self._maybe_welcome()
        self._check_rosetta()

    def _maybe_welcome(self) -> bool:
        """Show the welcome on the very first launch only. It never installs anything. Returns True if shown."""
        flag = self.welcome_flag()
        if os.environ.get("BREWCAT_NO_WELCOME") or os.path.exists(flag):
            return False
        try:  # written before showing, so closing it in any way (Skip, X, quit) still counts as seen
            os.makedirs(os.path.dirname(flag), exist_ok=True)
            open(flag, "w").close()
        except OSError:
            pass
        dlg = WelcomeDialog(self)
        self.wait_window(dlg)
        if dlg.choice:
            self.show_starter_kits(dlg.choice)
        return True

    def show_starter_kits(self, profile_label: str) -> None:
        """Set the profile, switch to the Kits view and select the first kit. Does not install anything."""
        if profile_label in dict(PROFILES):
            self.profile.set(profile_label)
        self.category = KITS
        self.notebook.select(0)
        self._fill_categories()
        self.refresh()
        rows = self.tree.get_children()
        if rows:
            self.tree.selection_set(rows[0])
            self.tree.focus(rows[0])
            self.tree.see(rows[0])
            self._on_select()

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
                r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=900,
                                   check=False)
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
                                         text=True, timeout=30, check=False).stdout
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
                                     capture_output=True, text=True, timeout=30,
                                     check=False).stdout.strip()
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
        essentials = {k for p in ([prof] if prof else cd.ESSENTIALS) for k in cd.ESSENTIALS[p]}
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
            if item.key in essentials:
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
        self._sync_retry()

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
        can = self.brew is not None and not self.busy and not self._planning

        def st(ok: bool) -> str:
            return "normal" if ok else "disabled"

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
        if item.homepage:
            return item.homepage
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
            items = [i for i in self.kit_items(obj) if not self.is_installed(i)]
            cmds = cd.install_commands(items)
        elif obj is not None:
            items = [obj]
            cmds = [obj.install_cmd]
        else:
            return
        if cmds:
            lines = "\n".join("brew " + " ".join(c) for c in cmds)
            self._confirm_install("Confirm installation", items, cmds, f"Run the following?\n\n{lines}")
        else:
            self._log("info", "Everything in this kit is already installed.\n")

    # ───────────────── confirmation with the install plan ─────────────────
    def _confirm_install(self, title: str, items: List[cd.Item], cmds: List[List[str]], fallback: str) -> None:
        """Always ask before installing. The plan (what will change) is computed in a worker thread so the window
        stays responsive; if it cannot be computed the plain confirmation `fallback` is used instead, so a plan
        problem never blocks an install."""
        if self._planning:
            return
        if not self.brew or not items:
            self._ask_and_run(title, None, cmds, fallback)
            return
        self._planning = True
        self._set_status("Checking what will change…")
        self.progress.start(12)
        self._on_select()  # disables the install buttons while planning
        brew = self.brew

        def worker() -> None:
            text: Optional[str] = None
            try:
                import plan as plan_mod  # lazy: only needed when installing
                text = plan_mod.format_plan(plan_mod.build_plan(brew, items))
            except Exception:  # noqa: BLE001 - any failure falls back to the plain confirmation
                text = None
            self.log_q.put(("call", lambda: self._plan_ready(title, text, cmds, fallback)))

        threading.Thread(target=worker, daemon=True).start()

    def _plan_ready(self, title: str, text: Optional[str], cmds: List[List[str]], fallback: str) -> None:
        self._planning = False
        self._set_status("")
        if not self.busy:
            self.progress.stop()
        self._on_select()
        self._ask_and_run(title, text, cmds, fallback)

    def _ask_and_run(self, title: str, plan_text: Optional[str], cmds: List[List[str]], fallback: str) -> None:
        if plan_text:
            lines = "\n".join("brew " + " ".join(c) for c in cmds)
            ok = self._ask_plan(title, f"{plan_text}\n\nWill run:\n{lines}")
        else:
            ok = messagebox.askyesno(title, fallback)
        if ok:
            self.run_brew(cmds)

    def _ask_plan(self, title: str, text: str) -> bool:
        dlg = ConfirmDialog(self, title, text)
        self.wait_window(dlg)  # the only blocking call; tests patch it
        return dlg.result

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
        self._confirm_install("Install list", items, [i.install_cmd for i in items],
                              f"Install {len(items)} packages?\n\n" + ", ".join(i.name for i in items))

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
    def _log(self, tag: str, text: str) -> None:
        self.log.config(state="normal")
        self.log.insert("end", text)
        self.log.see("end")
        self.log.config(state="disabled")

    def _set_status(self, text: str) -> None:
        self.status_var.set(text)

    def _drain_log(self) -> None:
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
                    self._log(tag, str(text))
        except queue.Empty:
            pass

    def _poll_log(self) -> None:
        self._drain_log()
        self.after(100, self._poll_log)

    def _finish(self) -> None:
        self.busy = False
        self.progress.stop()
        self._sync_retry()
        self.refresh_installed()

    def _sync_retry(self) -> None:
        can = bool(self.failed_cmds) and self.brew is not None and not self.busy and not self._planning
        self.btn_retry.config(state="normal" if can else "disabled")

    def copy_log(self) -> None:
        self.clipboard_clear()
        self.clipboard_append(self.log.get("1.0", "end-1c"))
        self._set_status("Log copied to clipboard.")

    def _batch_summary(self, result: BatchResult, cancelled: bool) -> None:
        """Say how the batch went and remember what failed so it can be retried (stopped runs are not failures)."""
        self.failed_cmds = []
        if cancelled:
            self._set_status("Stopped.")
            self._log("info", "\nStopped before finishing.\n")
            return
        failed, other, ok = result.failed_installs(), result.failed_other(), result.succeeded()
        if failed or other:
            self.failed_cmds = result.retry_commands()
            bits = []
            if failed:
                bits.append(f"{len(failed)} package{'s' if len(failed) != 1 else ''} failed: {', '.join(failed)}")
            if other:
                bits.append(f"{len(other)} command{'s' if len(other) != 1 else ''} failed: {', '.join(other)}")
            if ok:
                bits.append(f"{len(ok)} installed")
            line = "✗ " + "; ".join(bits)
            if failed:
                line += ". Use Retry failed to try those again, or Copy log to report it."
            else:
                line += ". Use Copy log to report it."
        elif ok:
            line = f"✓ {len(ok)} package{'s' if len(ok) != 1 else ''} installed successfully."
        else:
            line = "✓ Done."
        self._log("info", f"\n{line}\n")
        self._set_status(line)

    def retry_failed(self) -> None:
        """Re-run the install for ONLY the packages that failed, through the usual confirmation."""
        if self.busy or self._planning or not self.failed_cmds:
            return
        cmds = [list(c) for c in self.failed_cmds]
        lines = "\n".join("brew " + " ".join(c) for c in cmds)
        self._confirm_install("Retry failed installs", self._items_for(cmds), cmds,
                              f"Run the following?\n\n{lines}")

    @staticmethod
    def _items_for(cmds: List[List[str]]) -> List[cd.Item]:
        items: List[cd.Item] = []
        for cmd in cmds:
            kind = "cask" if "--cask" in cmd else "formula"
            for name in (a for a in cmd[1:] if not a.startswith("-")):
                found = next((i for i in cd.BY_KEY.values() if i.kind == kind and i.full_name == name), None)
                if found is not None and found not in items:
                    items.append(found)
        return items

    def run_brew(self, cmds: List[List[str]]) -> None:
        if not self.brew:
            messagebox.showerror("Homebrew", "brew not found. Install it from https://brew.sh")
            return
        if self.busy:
            return
        self.busy = True
        self.failed_cmds = []
        self._set_status("Running brew…")
        self.progress.start(12)
        self._on_select()
        env = dict(os.environ, HOMEBREW_NO_ANALYTICS="1", HOMEBREW_NO_COLOR="1",
                   HOMEBREW_NO_ENV_HINTS="1", NONINTERACTIVE="1")
        askpass = ensure_askpass()
        self.runner.reset()
        result = BatchResult()

        def emit(tag: str, text: str) -> None:
            self.log_q.put((tag, text))

        def run_one(args: List[str]) -> int:
            self.log_q.put(("cmd", f"\n$ brew {' '.join(args)}\n"))
            cmd_env = dict(env)
            # Only cask installs may need sudo; expose the askpass helper to those commands alone, and
            # tell the dialog which package(s) ask for the password.
            if askpass and args and args[0] in ("install", "reinstall") and "--cask" in args:
                cmd_env["SUDO_ASKPASS"] = askpass
                cmd_env["BREWCAT_PKG"] = ", ".join(a for a in args[1:] if not a.startswith("-"))
            code = self.runner.run(self.brew_cmd(*args), emit, cmd_env)
            result.record(args, code)
            return code

        def on_retry() -> None:
            if not self.runner.cancelled:
                self.log_q.put(("info", "↻ batch failed, retrying package by package…\n"))

        def worker() -> None:
            for args in cmds:
                if self.runner.cancelled:
                    break
                install_with_retry(run_one, args, on_retry)
            cancelled = self.runner.cancelled
            self.log_q.put(("call", lambda: self._batch_summary(result, cancelled)))
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
                                         text=True, timeout=60, check=False).stdout
                    res[kind] = set(out.split())
                except (OSError, subprocess.SubprocessError):
                    res[kind] = set()
            self.log_q.put(("installed", res))

        threading.Thread(target=worker, daemon=True).start()

    def _set_installed(self, res: Dict[str, Set[str]]) -> None:
        self.installed = res
        self.refresh()
