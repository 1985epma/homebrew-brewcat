"""brewcat command line: argument parsing and `brewcat doctor`.

Everything here runs without opening a window and without importing tkinter at module level, so it
works over SSH, in CI and on machines where the GUI cannot start.

Exit codes: 0 success, 1 a check failed or an operation failed, 2 invalid usage."""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

import brewenv
import catalog_data as cd
from help_text import HELP, VERSION, os_description

TAP = "1985epma/brewcat"
OK, WARN, FAIL = "OK", "WARN", "FAIL"


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # argparse prints usage and exits with 2 by default
        self.print_usage(sys.stderr)
        self.exit(2, f"brewcat: error: {message}\nTry `brewcat --help`.\n")


def build_parser() -> argparse.ArgumentParser:
    p = _Parser(prog="brewcat", add_help=False, usage="brewcat [-h] [-V] [--install-app] [command]  (commands: doctor search list kits install export profiles help)")
    p.add_argument("-h", "--help", action="store_true", help="show the full help")
    p.add_argument("-V", "--version", action="store_true", help="show the version and OS")
    p.add_argument("--install-app", action="store_true",
                   help="macOS: (re)create ~/Applications/brewcat.app for Launchpad/Spotlight")
    sub = p.add_subparsers(dest="command", metavar="command")
    doc = sub.add_parser("doctor", add_help=False, help="check this machine and print how to fix problems")
    doc.add_argument("--json", action="store_true", help="machine-readable output")
    sub.add_parser("help", add_help=False, help="show the full help")

    def filters(sp, with_query: bool = False) -> None:
        if with_query:
            sp.add_argument("query", nargs="*", help="words to look for (name, description, tags)")
        sp.add_argument("-p", "--profile", choices=sorted(cd.PROFILE_SLUGS), help="limit to one profile")
        sp.add_argument("--platform", choices=[cd.MAC, cd.LINUX], default=_default_platform(),
                        help="mac or linux (default: this machine)")
        sp.add_argument("--json", action="store_true", help="machine-readable output")

    sp = sub.add_parser("search", add_help=False, help="search the curated catalog")
    filters(sp, with_query=True)
    sp.add_argument("-c", "--category", help="limit to one category")
    sp.add_argument("--installed", action="store_true", help="only packages already installed")
    sp.add_argument("--not-installed", action="store_true", help="only packages not installed yet")
    sp = sub.add_parser("list", add_help=False, help="list the catalog (or one profile's categories)")
    filters(sp)
    sp.add_argument("-c", "--category", help="limit to one category")
    sp.add_argument("--installed", action="store_true", help="only packages already installed")
    sp.add_argument("--not-installed", action="store_true", help="only packages not installed yet")
    sp = sub.add_parser("kits", add_help=False, help="list kits, or show one kit's packages")
    sp.add_argument("name", nargs="?", help="kit name (or unique prefix) to show its packages")
    sp.add_argument("-p", "--profile", choices=sorted(cd.PROFILE_SLUGS))
    sp.add_argument("--platform", choices=[cd.MAC, cd.LINUX], default=_default_platform())
    sp.add_argument("--json", action="store_true")
    sp = sub.add_parser("install", add_help=False, help="install a kit or a package")
    sp.add_argument("target", help="kit name or package name (use formula:NAME or cask:NAME if ambiguous)")
    sp.add_argument("--platform", choices=[cd.MAC, cd.LINUX], default=_default_platform())
    sp.add_argument("-n", "--dry-run", action="store_true", help="print the brew commands, run nothing")
    sp.add_argument("-y", "--yes", action="store_true", help="do not ask for confirmation")
    sp = sub.add_parser("export", add_help=False, help="write a kit (or packages) as a Brewfile")
    sp.add_argument("target", nargs="+", help="kit name, or one or more package names")
    sp.add_argument("--platform", choices=[cd.MAC, cd.LINUX], default=_default_platform())
    sp.add_argument("-o", "--output", help="file to write (default: standard output)")
    sub.add_parser("profiles", add_help=False, help="list the profile names for --profile")
    return p


# ───────────────────────── doctor ─────────────────────────
def _check(name: str, status: str, detail: str, hint: str = "") -> Dict[str, str]:
    return {"name": name, "status": status, "detail": detail, "hint": hint}


def _run(cmd: List[str], timeout: int = 15) -> str:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def _trusted_entries() -> List[str]:
    cfg = os.environ.get("XDG_CONFIG_HOME")
    path = Path(cfg) / "homebrew/trust.json" if cfg else Path.home() / ".homebrew/trust.json"
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return []
    return [e for v in data.values() if isinstance(v, list) for e in v if isinstance(e, str)]


def collect_checks() -> List[Dict[str, str]]:
    checks: List[Dict[str, str]] = []
    mac = sys.platform == "darwin"
    silicon = brewenv.apple_silicon()

    checks.append(_check("brewcat", OK, f"{VERSION}"))
    checks.append(_check("system", OK, os_description()))

    translated = mac and silicon and platform.machine() != "arm64"
    if translated:
        checks.append(_check("rosetta translation", WARN,
                             "this process runs under Rosetta (x86_64) on Apple Silicon",
                             "Use the Homebrew Python (/opt/homebrew/bin/python3) or launch brewcat from a "
                             "native (arm64) terminal"))
    if mac and silicon:
        has_rosetta = os.path.exists("/Library/Apple/usr/share/rosetta/rosetta")
        checks.append(_check("rosetta 2", OK if has_rosetta else WARN,
                             "installed" if has_rosetta else "not installed (only needed for Intel-only apps)",
                             "" if has_rosetta else "softwareupdate --install-rosetta --agree-to-license"))

    py = f"{platform.python_version()} ({sys.executable})"
    checks.append(_check("python", OK, py))
    try:
        import tkinter  # noqa: PLC0415 - imported lazily so the CLI works without Tk
        tk_ver = float(tkinter.TkVersion)
        if mac and tk_ver < 8.6:
            checks.append(_check("tk", WARN, f"Tk {tk_ver:g}: windows can render blank on recent macOS",
                                 "brew install python-tk"))
        else:
            checks.append(_check("tk", OK, f"Tk {tk_ver:g}"))
    except ImportError:
        checks.append(_check("tk", FAIL, "tkinter is not available",
                             "brew install python-tk  (Linux: python3-tk from your distro)"))
    if not mac:
        has_display = bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
        checks.append(_check("display", OK if has_display else WARN,
                             "graphical session found" if has_display else "no DISPLAY/WAYLAND_DISPLAY",
                             "" if has_display else "the window needs a graphical session"))

    brew = brewenv.find_brew()
    if not brew:
        checks.append(_check("homebrew", FAIL, "brew not found", "Install Homebrew from https://brew.sh"))
    else:
        version = (_run([brew, "--version"]).splitlines() or ["unknown"])[0]
        checks.append(_check("homebrew", OK, f"{version} ({brew})"))
        if mac and silicon and brew.startswith("/usr/local"):
            checks.append(_check("homebrew architecture", WARN,
                                 "Intel Homebrew (/usr/local) on an Apple Silicon Mac",
                                 "Native Homebrew lives in /opt/homebrew; brewcat runs brew via `arch` when needed"))
        tap_dir = Path(_run([brew, "--repository"]) or "/nonexistent") / "Library/Taps/1985epma/homebrew-brewcat"
        if tap_dir.exists():
            trusted = any(e == TAP or e.startswith(TAP + "/") for e in _trusted_entries())
            checks.append(_check("brewcat tap", OK if trusted else WARN,
                                 f"{TAP} is {'trusted' if trusted else 'not trusted'}",
                                 "" if trusted else f"brew trust {TAP}"))

    if shutil.which("git"):
        checks.append(_check("git", OK, _run(["git", "--version"])))
    else:
        checks.append(_check("git", WARN, "git not found (needed to install skills from GitHub)",
                             "Install git (brew install git)"))

    if mac:
        user_app = Path.home() / "Applications/brewcat.app"
        sys_app = Path("/Applications/brewcat.app")
        if user_app.exists() or sys_app.exists():
            where = "~/Applications" if user_app.exists() else "/Applications"
            checks.append(_check("brewcat.app", OK, f"found in {where}"))
        else:
            checks.append(_check("brewcat.app", WARN, "not in ~/Applications or /Applications",
                                 "Run `brewcat --install-app` or `brew install --cask 1985epma/brewcat/brewcat`"))
        askpass = Path.home() / "Library/Application Support/brewcat/askpass.sh"
        checks.append(_check("sudo password dialog", OK if askpass.exists() else WARN,
                             "askpass helper ready" if askpass.exists() else "created on first cask install"))
    return checks


def doctor(as_json: bool) -> int:
    checks = collect_checks()
    failed = any(c["status"] == FAIL for c in checks)
    if as_json:
        print(json.dumps({"version": VERSION, "ok": not failed, "checks": checks}, indent=2))
    else:
        width = max(len(c["name"]) for c in checks)
        for c in checks:
            print(f"[{c['status']:<4}] {c['name']:<{width}}  {c['detail']}")
            if c["hint"]:
                print(f"       {'':<{width}}  → {c['hint']}")
        warns = sum(c["status"] == WARN for c in checks)
        print(f"\n{'Problems found' if failed else 'No blocking problems'}"
              f"{f' ({warns} warning(s))' if warns else ''}.")
    return 1 if failed else 0


# ───────────────────────── catalog commands (no window) ─────────────────────────
def _default_platform() -> str:
    return cd.MAC if sys.platform == "darwin" else cd.LINUX


def _installed() -> Optional[Dict[str, set]]:
    """{'formula': {...}, 'cask': {...}} from brew, or None when brew is missing."""
    brew = brewenv.find_brew()
    if not brew:
        return None
    return {kind: set(_run(brewenv.brew_command(brew, "list", f"--{kind}", "-1"), timeout=60).split())
            for kind in ("formula", "cask")}


def _item_dict(i: "cd.Item", installed: Optional[Dict[str, set]]) -> Dict[str, object]:
    d: Dict[str, object] = {"name": i.full_name, "kind": i.kind, "category": i.category,
                            "description": i.desc, "profiles": list(i.profiles),
                            "platforms": list(i.platforms)}
    if installed is not None:
        d["installed"] = i.name in installed[i.kind]
    return d


def _print_items(items: List["cd.Item"], installed: Optional[Dict[str, set]], as_json: bool) -> None:
    if as_json:
        print(json.dumps([_item_dict(i, installed) for i in items], indent=2))
        return
    width = shutil.get_terminal_size((100, 20)).columns
    name_w = max((len(i.full_name) for i in items), default=4)
    cat_w = min(max((len(i.category) for i in items), default=8), 26)
    for i in items:
        mark = " " if installed is None else ("✓" if i.name in installed[i.kind] else " ")
        head = f"{mark} {i.full_name:<{name_w}}  {i.kind:<7} {i.category[:cat_w]:<{cat_w}}  "
        print((head + i.desc)[: max(width, 60)])


def _select(ns: argparse.Namespace, query: str = "") -> List["cd.Item"]:
    profile = cd.PROFILE_SLUGS.get(ns.profile) if getattr(ns, "profile", None) else None
    items = cd.find_items(query, profile, ns.platform, getattr(ns, "category", None))
    if getattr(ns, "installed", False) or getattr(ns, "not_installed", False):
        installed = _installed()
        if installed is None:
            print("brewcat: brew not found, cannot tell what is installed", file=sys.stderr)
            return []
        want = bool(ns.installed)
        items = [i for i in items if (i.name in installed[i.kind]) == want]
    return items


def cmd_search(ns: argparse.Namespace) -> int:
    items = _select(ns, " ".join(ns.query))
    if not items:
        print("brewcat: nothing found. Try `brewcat list`, or `brew search` for all of Homebrew.", file=sys.stderr)
        return 1
    _print_items(items, _installed(), ns.json)
    return 0


def cmd_list(ns: argparse.Namespace) -> int:
    items = _select(ns)
    if not items:
        print("brewcat: nothing matches those filters.", file=sys.stderr)
        return 1
    _print_items(items, _installed(), ns.json)
    return 0


def cmd_profiles(_ns: argparse.Namespace) -> int:
    for slug in sorted(cd.PROFILE_SLUGS):
        n = sum(cd.PROFILE_SLUGS[slug] in i.profiles for i in cd.ITEMS)
        print(f"{slug:<12} {n} packages")
    return 0


def _kit_items(kit: "cd.Kit", platform_: str) -> List["cd.Item"]:
    return [cd.BY_KEY[k] for k in kit.keys if platform_ in cd.BY_KEY[k].platforms]


def cmd_kits(ns: argparse.Namespace) -> int:
    if ns.name:
        kit = cd.find_kit(ns.name)
        if not kit:
            print(f"brewcat: no kit matches '{ns.name}' (run `brewcat kits`)", file=sys.stderr)
            return 1
        _print_items(_kit_items(kit, ns.platform), _installed(), ns.json)
        return 0
    profile = cd.PROFILE_SLUGS.get(ns.profile) if ns.profile else None
    kits = [k for k in cd.KITS if not profile or k.profile == profile]
    if ns.json:
        print(json.dumps([{"name": k.name, "description": k.desc, "profile": k.profile,
                           "packages": [cd.BY_KEY[x].full_name for x in k.keys]} for k in kits], indent=2))
    else:
        for k in kits:
            print(f"{k.name:<34} {k.profile:<12} {len(k.keys):>2} packages  {k.desc}")
    return 0


def _resolve_install_target(target: str, platform_: str):
    """Returns (label, items) or an error message string."""
    kit = cd.find_kit(target)
    if kit:
        return kit.name, _kit_items(kit, platform_)
    hits = [i for i in cd.resolve_packages(target) if platform_ in i.platforms]
    if not hits:
        return f"nothing called '{target}' in the catalog (try `brewcat search {target}`)"
    if len(hits) > 1:
        return f"'{target}' is ambiguous: use " + " or ".join(i.key for i in hits)
    return hits[0].full_name, hits


def cmd_install(ns: argparse.Namespace) -> int:
    res = _resolve_install_target(ns.target, ns.platform)
    if isinstance(res, str):
        print(f"brewcat: {res}", file=sys.stderr)
        return 1
    label, items = res
    brew = brewenv.find_brew()
    installed = _installed() if brew else None
    todo = [i for i in items if installed is None or i.name not in installed[i.kind]]
    if not todo:
        print(f"Everything in '{label}' is already installed.")
        return 0
    cmds = [i.install_cmd for i in todo]
    printable = ["brew " + " ".join(c) for c in cmds]
    print(f"Plan for '{label}' ({len(todo)} package(s)):")
    print("\n".join("  " + p for p in printable))
    if ns.dry_run:
        return 0
    if not brew:
        print("brewcat: brew not found. Install Homebrew from https://brew.sh", file=sys.stderr)
        return 1
    if not ns.yes:
        if not sys.stdin.isatty():
            print("brewcat: confirmation needed but there is no terminal; pass --yes to proceed.", file=sys.stderr)
            return 2
        if input("Install these? [y/N] ").strip().lower() not in ("y", "yes"):
            print("Cancelled.")
            return 1
    failed = 0
    for c in cmds:
        print(f"\n$ brew {' '.join(c)}", flush=True)
        failed += subprocess.run(brewenv.brew_command(brew, *c)).returncode != 0
    return 1 if failed else 0


def cmd_export(ns: argparse.Namespace) -> int:
    items: List["cd.Item"] = []
    first = cd.find_kit(ns.target[0]) if len(ns.target) == 1 else None
    if first:
        items = _kit_items(first, ns.platform)
    else:
        for name in ns.target:
            hits = [i for i in cd.resolve_packages(name) if ns.platform in i.platforms]
            if len(hits) != 1:
                print(f"brewcat: '{name}' is {'ambiguous (use formula:NAME or cask:NAME)' if hits else 'not in the catalog'}",
                      file=sys.stderr)
                return 1
            items.append(hits[0])
    text = "\n".join(cd.brewfile_lines(items)) + "\n"
    if ns.output:
        Path(ns.output).write_text(text)
        print(f"Wrote {len(items)} package(s) to {ns.output}  (use: brew bundle --file={ns.output})", file=sys.stderr)
    else:
        sys.stdout.write(text)
    return 0


COMMANDS = {"search": cmd_search, "list": cmd_list, "kits": cmd_kits, "install": cmd_install,
            "export": cmd_export, "profiles": cmd_profiles}


# ───────────────────────── entry ─────────────────────────
def run(argv: Optional[List[str]] = None) -> Optional[int]:
    """Handle command-line usage. Returns an exit code, or None to open the window."""
    args = list(sys.argv[1:] if argv is None else argv)
    args = [a for a in args if not a.startswith("-psn_")]  # old macOS Finder launch argument
    ns = build_parser().parse_args(args)
    if ns.help or ns.command == "help":
        print(HELP)
        return 0
    if ns.version:
        print(f"brewcat {VERSION}\n{os_description()}")
        return 0
    if ns.install_app:
        if sys.platform != "darwin":
            print("--install-app is only needed on macOS (the Linux installer adds a desktop entry).")
            return 0
        import launcher  # noqa: PLC0415
        try:
            ok = launcher.build_app_bundle()
        except Exception as exc:  # noqa: BLE001
            print(f"Could not create the app: {exc}", file=sys.stderr)
            return 1
        print("Created ~/Applications/brewcat.app: open it from Launchpad or Spotlight." if ok
              else "Could not create ~/Applications/brewcat.app.")
        return 0 if ok else 1
    if ns.command == "doctor":
        return doctor(ns.json)
    if ns.command in COMMANDS:
        return COMMANDS[ns.command](ns)
    return None
