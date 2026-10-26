#!/usr/bin/env python3
"""Check the curated catalog against Homebrew's public API.

  scripts/validate_catalog.py            structure + every package must exist in Homebrew
  scripts/validate_catalog.py --offline  structure only (no network)

Errors (exit 1): unknown/disabled packages, duplicate keys, kits or essentials pointing to missing items.
Warnings (exit 0): deprecated packages. Packages from third-party taps (e.g. hashicorp/tap) are skipped.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import catalog_data as cd  # noqa: E402

API = "https://formulae.brew.sh/api/{kind}.json"


def structure_errors() -> list:
    errors = [f"duplicate key: {k}" for k, n in Counter(i.key for i in cd.ITEMS).items() if n > 1]
    for kit in cd.KITS:
        errors += [f"kit '{kit.name}' references missing {k}" for k in kit.keys if k not in cd.BY_KEY]
    for profile, keys in cd.ESSENTIALS.items():
        errors += [f"essentials[{profile}] references missing {k}" for k in keys if k not in cd.BY_KEY]
    return errors


def fetch(kind: str) -> list:
    req = urllib.request.Request(API.format(kind=kind), headers={"User-Agent": "brewcat-validate"})
    with urllib.request.urlopen(req, timeout=120) as r:  # noqa: S310 - fixed https URL
        return json.load(r)


def index(entries: list, kind: str) -> dict:
    """name/alias/old name -> entry"""
    out = {}
    for e in entries:
        names = [e["token"]] + e.get("old_tokens", []) if kind == "cask" else [e["name"]] + e.get("aliases", []) + e.get("oldnames", [])
        for n in names:
            out.setdefault(n, e)
    return out


def main() -> int:
    errors, warnings = structure_errors(), []
    if "--offline" not in sys.argv:
        idx = {kind: index(fetch(kind), kind) for kind in ("formula", "cask")}
        for i in cd.ITEMS:
            if i.tap:
                continue
            entry = idx[i.kind].get(i.name)
            if entry is None:
                errors.append(f"{i.key}: not found in Homebrew (renamed or removed?)")
            elif entry.get("disabled"):
                errors.append(f"{i.key}: disabled in Homebrew")
            elif entry.get("deprecated"):
                warnings.append(f"{i.key}: deprecated in Homebrew")
    for w in warnings:
        print(f"WARN  {w}")
    for e in errors:
        print(f"ERROR {e}")
    print(f"{len(cd.ITEMS)} packages, {len(cd.KITS)} kits: {len(errors)} error(s), {len(warnings)} warning(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
