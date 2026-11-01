"""What an install would change: shared by `brewcat install` and the window (no tkinter import).

Only facts Homebrew can tell us are reported: which packages are new, which are installed already, which are
outdated and which extra dependencies `brew install --dry-run` says it would also install. Homebrew gives no
download size or install time without downloading, so none is guessed here. Nothing in this module raises: when
brew cannot answer, the plan says so in `notes`."""
from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Set, Tuple

import brewenv
import catalog_data

MAX_LISTED = 30  # extra dependencies printed by format_plan before "… and N more"

_DEPS_HEADER = re.compile(r"^==> Would install \d+ dependenc(?:y|ies)\b")
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9@+._/-]*$")


@dataclass(frozen=True)
class Plan:
    to_install: List[str]  # Item.full_name of packages that are not installed yet (formulae and casks)
    already_installed: List[str]
    outdated: List[str]  # installed AND listed by `brew outdated` (empty if unknown)
    extra_deps: List[str]  # extra dependencies brew would also install (from `brew install --dry-run`)
    notes: List[str]  # e.g. "2 cask(s): the installer may ask for your administrator password"
    casks: List[str] = field(default_factory=list)  # which of the names above are casks (the rest are formulae)


def _brew(brew: str, args: Sequence[str], timeout: float) -> Optional[Tuple[int, str]]:
    """(exit code, stdout) of a read-only brew call, or None if brew could not be run in time."""
    env = dict(os.environ, HOMEBREW_NO_AUTO_UPDATE="1")  # a plan must be quick and must not update Homebrew
    try:
        res = subprocess.run(brewenv.brew_command(brew, *args), capture_output=True, text=True, timeout=timeout,
                             check=False, env=env)
    except (OSError, subprocess.SubprocessError):
        return None
    return res.returncode, res.stdout


def parse_dry_run(text: str, requested: Sequence[str]) -> List[str]:
    """Names of the dependencies `brew install --dry-run` lists beyond `requested`. Output looks like:
        ==> Would install 1 formula:          (the requested packages: skipped)
        jq 1.8.2
        ==> Would install 1 dependency for jq:
        oniguruma 6.9.10"""
    skip: Set[str] = set(requested) | {r.rsplit("/", 1)[-1] for r in requested}
    deps: List[str] = []
    in_deps = False
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("==>"):
            in_deps = bool(_DEPS_HEADER.match(line))
            continue
        if not line:
            in_deps = False
        elif in_deps:
            name = line.split()[0]
            if _NAME.match(name) and name not in skip and name not in deps:
                deps.append(name)
    return deps


def _installed_names(brew: str, kind: str, timeout: float) -> Optional[Set[str]]:
    res = _brew(brew, ["list", f"--{kind}", "-1"], timeout)
    return set(res[1].split()) if res and res[0] == 0 else None


def build_plan(brew: str, items: Sequence["catalog_data.Item"], timeout: float = 60.0) -> Plan:
    """Classify `items` and ask brew which extra dependencies they would pull in. At most five brew calls
    (two `list`, one `outdated`, one dry run per kind), never one per package. Never raises."""
    notes: List[str] = []
    installed = {kind: _installed_names(brew, kind, timeout) for kind in ("formula", "cask")}
    for kind in ("formula", "cask"):
        if installed[kind] is None and any(i.kind == kind for i in items):
            notes.append(f"could not read the installed {kind} list: every {kind} is shown as new")

    def have(i: "catalog_data.Item") -> bool:
        names = installed[i.kind]
        return names is not None and (i.name in names or i.full_name in names)

    todo = [i for i in items if not have(i)]
    done = [i for i in items if have(i)]

    outdated: List[str] = []
    if done:
        res = _brew(brew, ["outdated", "--quiet"], timeout)
        if res and res[0] == 0:
            listed = set(res[1].split())
            outdated = [i.full_name for i in done if i.name in listed or i.full_name in listed]
        else:
            notes.append("could not check for outdated packages")

    extra: List[str] = []
    failed = False
    for kind in ("formula", "cask"):
        names = [i.full_name for i in todo if i.kind == kind]
        if not names:
            continue
        res = _brew(brew, ["install", "--dry-run", *(["--cask"] if kind == "cask" else []), *names], timeout)
        if not res or res[0] != 0:
            failed = True
            continue
        extra += [d for d in parse_dry_run(res[1], names) if d not in extra]
    if failed:
        notes.append("could not check dependencies: brew install --dry-run failed or timed out")

    ncask = sum(i.kind == "cask" for i in todo)
    if ncask:
        notes.append(f"{ncask} cask(s): the installer may ask for your administrator password")
    return Plan(to_install=[i.full_name for i in todo], already_installed=[i.full_name for i in done],
                outdated=outdated, extra_deps=extra, notes=notes,
                casks=[i.full_name for i in items if i.kind == "cask"])


def _names(label: str, names: Sequence[str], limit: int = MAX_LISTED) -> str:
    shown = ", ".join(names[:limit]) + (f", … and {len(names) - limit} more" if len(names) > limit else "")
    return f"  {label}: {shown}"


def format_plan(plan: Plan) -> str:
    """Plain multi-line text (no colours): a one-line summary, then the names behind each count."""
    parts = [f"{len(plan.to_install)} to install"]
    if plan.extra_deps:
        parts.append(f"{len(plan.extra_deps)} extra dependenc{'y' if len(plan.extra_deps) == 1 else 'ies'}")
    if plan.already_installed:
        parts.append(f"{len(plan.already_installed)} already installed")
    if plan.outdated:
        parts.append(f"{len(plan.outdated)} outdated")
    lines = ["Summary: " + ", ".join(parts) + "."]
    if plan.to_install:
        lines.append(_names("To install", plan.to_install))
    if plan.extra_deps:
        lines.append(_names("Also installed as dependencies", plan.extra_deps))
    if plan.already_installed:
        lines.append(_names("Already installed", plan.already_installed))
    if plan.outdated:
        lines.append(_names("Outdated (brew upgrade updates them)", plan.outdated))
    lines += [f"  Note: {n}" for n in plan.notes]
    return "\n".join(lines)
