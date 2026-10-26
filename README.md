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
    brew install brewcat
    brewcat

## Other install options

**macOS (.dmg):** download `brewcat-<version>.dmg` from [Releases](https://github.com/1985epma/homebrew-brewcat/releases), drag *brewcat* to Applications. The app is not notarized by Apple, so macOS may say it "could not verify brewcat is free of malware". Fix it once with:

    xattr -dr com.apple.quarantine /Applications/brewcat.app

(or System Settings → Privacy & Security → *Open Anyway*). Installing with `brew` avoids this warning entirely. It needs `brew install python-tk`.

**Linux (script):**

    curl -fsSL https://raw.githubusercontent.com/1985epma/homebrew-brewcat/main/install.sh | bash

Installs to `~/.local/share/brewcat`, adds a `brewcat` command and a desktop entry.

**Build the .dmg yourself (macOS):** `./scripts/build-dmg.sh 0.1.2.1`

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
