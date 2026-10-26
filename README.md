# brewcat

A visual catalog (Python + Tkinter) of Homebrew packages for developers and gamers, on macOS and Linux.

- Categories, search, and filters by profile (Dev/Gamer) and platform
- ✨ Suggestions based on what you already have installed
- 🏗️ SRE/Cloud profile: Terraform, AWS, Google Cloud, Azure, Railway, Kubernetes, observability
- 🧰 Dev areas: Node.js, Go, .NET, Java, Shell/Unix, Mainframe
- 🔎 Search any Homebrew package by name (not just the curated catalog)
- ✅ Always asks for confirmation before installing
- 📦 Kits (Web Full-Stack, DevOps, Retro Gaming, Streamer…)
- 🧠 Skills: scan a GitHub repo (e.g. `anthropics/skills`) or local folder and install skills into Claude, Kiro and VS Code
- 🔌 MCP: install MCP servers (presets or custom) into the same three tools
- 🛒 Your own list: install everything at once or export a Brewfile
- 🔗 Each package shows its formulae.brew.sh page so you can research before installing

## Install with Homebrew

    brew tap 1985epma/brewcat
    brew trust 1985epma/brewcat
    brew install brewcat
    brewcat

Recent Homebrew versions refuse to load formulae from third-party taps until you trust them. If you see
`Refusing to load formula … from untrusted tap`, run `brew trust 1985epma/brewcat` once (then
`brew update && brew upgrade brewcat`).

## Appear in Launchpad / Applications (macOS)

- `brew install --cask 1985epma/brewcat/brewcat` installs **brewcat.app** into /Applications (Launchpad, Spotlight, Dock).
- With the formula (`brew install brewcat`), the first time you run `brewcat` it creates
  `~/Applications/brewcat.app` automatically, so it shows up in Launchpad and Spotlight. Re-create it with
  `brewcat --install-app`; opt out with `BREWCAT_NO_APP=1`.

## Other install options

**macOS (.dmg):** download `brewcat-<version>.dmg` from [Releases](https://github.com/1985epma/homebrew-brewcat/releases), drag *brewcat* to Applications. The app is not notarized by Apple, so macOS may say it "could not verify brewcat is free of malware". Fix it once with:

    xattr -dr com.apple.quarantine /Applications/brewcat.app

(or System Settings → Privacy & Security → *Open Anyway*). Installing with `brew` avoids this warning entirely. It needs `brew install python-tk`.

**Linux (script):**

    curl -fsSL https://raw.githubusercontent.com/1985epma/homebrew-brewcat/main/install.sh | bash

Installs to `~/.local/share/brewcat`, adds a `brewcat` command and a desktop entry. It installs the latest released tag (not the moving `main` branch); pin a version with `BREWCAT_REF=v0.1.2.6`.
Review the script before piping it to `bash`: https://github.com/1985epma/homebrew-brewcat/blob/main/install.sh

**Build the .dmg yourself (macOS):** `./scripts/build-dmg.sh`

## Command line

    brewcat --help        full help
    brewcat --version     version and OS
    brewcat doctor        checks Python/Tk, Homebrew, Rosetta, tap trust, app bundle… and prints how to fix them
    brewcat doctor --json machine-readable (exit code 1 if a check fails)
    brewcat search terraform -p sre          search the curated catalog without opening a window
    brewcat list -p security --not-installed list what you still miss in a profile (✓ = installed)
    brewcat kits -p sre                      list kits (brewcat kits "git pro" shows one kit)
    brewcat install "terraform + aws" -n     plan only; add --yes to skip the confirmation
    brewcat export "git pro" -o Brewfile     write a Brewfile (brew bundle --file=Brewfile)
    brewcat profiles                         profile names for -p (dev, sre, qa, security, gamer…)
    brewcat --install-app macOS: (re)create ~/Applications/brewcat.app

Exit codes: 0 success, 1 nothing found / a check or operation failed, 2 invalid usage.
`--json` is available on `search`, `list`, `kits` and `doctor`; data goes to stdout, messages to stderr.

## Development

    python -m pip install pytest ruff
    ruff check . && pytest          # 51 tests; the GUI smoke test needs a display (xvfb on Linux)
    python scripts/validate_catalog.py   # every catalog package must still exist in Homebrew

CI runs the same on Linux and macOS; a weekly job re-validates the catalog against Homebrew's API.

## Releasing (maintainers)

    scripts/release.sh 0.1.3                 # dry run: checks everything and prints the plan
    scripts/release.sh 0.1.3 --yes --notes "What changed"

The version lives in `help_text.py` only; the script bumps it, tags, builds the `.dmg`, creates the GitHub
release and sets the formula and cask sha256 from what GitHub actually serves. Tags are never moved.

## Run from source

    python3 app.py

On macOS, the system Python (Tk 8.5) shows a blank window, so the app automatically restarts with Homebrew's Python when available. Install it with `brew install python-tk`.
On Linux: `brew install python-tk` or your distro's `python3-tk` package.

## Where things are installed

| Target | Skills (user / project) | MCP config (user / project) |
|---|---|---|
| Claude | `~/.claude/skills` / `.claude/skills` | `~/.claude.json` / `.mcp.json` |
| Kiro | `~/.kiro/skills` / `.kiro/skills` | `~/.kiro/settings/mcp.json` / `.kiro/settings/mcp.json` |
| VS Code | `~/.copilot/skills` / `.github/skills` | user `mcp.json` / `.vscode/mcp.json` |

MCP configs are edited in place and a `.bak` copy is kept.

## License

[MIT](LICENSE)
