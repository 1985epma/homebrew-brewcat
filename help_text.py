"""Help text for brewcat, shared by `brewcat --help` and the in-app Help window."""

VERSION = "0.1.2.2"

HELP = f"""\
brewcat {VERSION} — a visual catalog of Homebrew packages, skills and MCP servers
for developers, SRE/cloud engineers and gamers (macOS and Linux).

USAGE
  brewcat              open the app
  brewcat --help       show this help
  brewcat --version    show the version

PACKAGES TAB
  Profile     All, Dev, SRE/Cloud, QA, Data Scientist, Data Engineer, Support & Network,
              Security, Design (web/video/graphics), DJ/Music, Office or Gamer. It filters the
              catalog, categories, kits and suggestions.
  Platform    mac or linux. Casks (GUI apps) exist only on macOS.
  Search      Type 2+ letters. Matches the curated catalog (name, description, tags) and
              also any package in Homebrew (via `brew search`), listed under
              "🔎 Homebrew search" and at the end of "★ All".
  Categories  ★ All · ✨ Suggestions · 📦 Kits · 🛒 My list · 🔎 Homebrew search · topic areas.
  ✨ Suggestions  Uninstalled packages that pair with what you already have, with the reason.
  📦 Kits         Ready-made bundles (Terraform + AWS, Kubernetes Admin, Retro Gaming…).
  🛒 My list      Double-click a package to add or remove it. Install the whole list at once
                  or export it as a Brewfile (brew bundle --file=Brewfile).
  Status      ✓ installed (green) · 🛒 in your list.
  Buttons     Install, Uninstall, Add to list, Copy command, Open page (formulae.brew.sh).
              The 🔗 link in the details panel opens the package page so you can research first.
  Top bar     "Refresh status" re-reads what is installed. "brew update" updates Homebrew.

SKILLS TAB
  1. Enter a GitHub repo (owner/repo or URL, e.g. anthropics/skills) or pick a local folder.
  2. Scan, select skills, choose where to install and click "Install selected skills".
  Targets      Claude, Kiro, VS Code. Scope: User (global) or Project (pick a folder).
  Locations    Claude  ~/.claude/skills   or <project>/.claude/skills
               Kiro    ~/.kiro/skills     or <project>/.kiro/skills
               VS Code ~/.copilot/skills  or <project>/.github/skills
  "C K V" column shows where a skill is already installed for the chosen scope.

MCP TAB
  Pick a preset (filesystem, memory, context7, playwright, fetch, git…) or type your own
  name, command, arguments and env (KEY=VALUE, comma-separated), then choose targets/scope.
  Config files   Claude  ~/.claude.json or <project>/.mcp.json
                 Kiro    ~/.kiro/settings/mcp.json or <project>/.kiro/settings/mcp.json
                 VS Code user mcp.json or <project>/.vscode/mcp.json
  A .bak copy of each config is kept. Most presets need node (npx) or uv (uvx).

SAFETY
  brewcat always asks for confirmation before installing or uninstalling anything.
  Command output appears in the log at the bottom of the window.

TROUBLESHOOTING
  "Refusing to load formula … from untrusted tap"   Run once: brew trust 1985epma/brewcat
  "Cannot install under Rosetta 2"  brewcat now runs brew natively (arch -arm64) on Apple Silicon.
  macOS asks for Rosetta 2  On Apple Silicon brewcat offers to install it at startup
                          (or run: softwareupdate --install-rosetta --agree-to-license).
  Blank window on macOS   The system Python's Tk 8.5 is broken: brew install python-tk
  "brew NOT found"        Install Homebrew from https://brew.sh
  Cask asks for a password  Run the shown `brew install --cask …` command in a terminal.

LINKS
  https://github.com/1985epma/homebrew-brewcat   (MIT License)
"""


def os_description() -> str:
    """Human-readable OS name, version and CPU architecture (flags Rosetta translation)."""
    import platform
    import subprocess
    import sys

    machine = platform.machine()
    if sys.platform == "darwin":
        name = f"macOS {platform.mac_ver()[0]}"
        try:
            out = subprocess.run(["/usr/sbin/sysctl", "-n", "hw.optional.arm64", "sysctl.proc_translated"],
                                 capture_output=True, text=True, timeout=5).stdout.split()
        except (OSError, subprocess.SubprocessError):
            out = []
        if machine == "x86_64" and out[:1] == ["1"]:
            return f"{name} ({machine}, Apple Silicon running under Rosetta)"
        return f"{name} ({'Apple Silicon, arm64' if machine == 'arm64' else machine})"
    try:
        name = platform.freedesktop_os_release().get("PRETTY_NAME", "Linux")
    except (OSError, AttributeError):
        name = f"{platform.system()} {platform.release()}"
    return f"{name} ({machine})"
