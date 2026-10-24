"""Curated catalog of Homebrew packages for developers and gamers.

Formulae work on macOS and Linux; casks (GUI apps) are macOS only.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple

DEV = "dev"
GAMER = "gamer"
MAC = "mac"
LINUX = "linux"
BOTH = (MAC, LINUX)


@dataclass(frozen=True)
class Item:
    name: str
    kind: str  # "formula" | "cask"
    category: str
    desc: str
    profiles: Tuple[str, ...]
    platforms: Tuple[str, ...]
    tags: Tuple[str, ...] = ()

    @property
    def key(self) -> str:
        return f"{self.kind}:{self.name}"

    @property
    def install_cmd(self) -> List[str]:
        cmd = ["install"]
        if self.kind == "cask":
            cmd.append("--cask")
        return cmd + [self.name]


@dataclass(frozen=True)
class Kit:
    name: str
    desc: str
    profile: str
    keys: Tuple[str, ...] = field(default_factory=tuple)


ITEMS: List[Item] = []


def _add(kind, category, profiles, platforms, rows):
    for name, desc, tags in rows:
        ITEMS.append(Item(name, kind, category, desc, tuple(profiles),
                          tuple(platforms), tuple(tags.split())))


def formula(category, rows, profiles=(DEV,), platforms=BOTH):
    _add("formula", category, profiles, platforms, rows)


def cask(category, rows, profiles=(DEV,), platforms=(MAC,)):
    _add("cask", category, profiles, platforms, rows)


# ───────────────────────── DEV ─────────────────────────
C_TERM = "Terminal & Shell"
formula(C_TERM, [
    ("starship", "Fast, customizable prompt for any shell", "shell terminal"),
    ("zsh-autosuggestions", "Command suggestions as you type (zsh)", "shell zsh"),
    ("zsh-syntax-highlighting", "Syntax highlighting on the command line (zsh)", "shell zsh"),
    ("tmux", "Terminal multiplexer: sessions, windows and panes", "terminal tmux"),
    ("zellij", "Modern terminal workspace, a tmux alternative", "terminal tmux rust"),
    ("fzf", "Interactive fuzzy finder for files, history and more", "cli search"),
    ("zoxide", "Smarter cd that learns your favorite directories", "cli shell"),
    ("atuin", "Shell history with search, context and sync", "shell cli"),
    ("bat", "cat with syntax highlighting and git integration", "cli"),
    ("eza", "Modern ls with colors, icons and git status", "cli"),
    ("ripgrep", "Blazing-fast grep that respects .gitignore", "cli search"),
    ("fd", "Simple and fast find", "cli search"),
    ("tldr", "Short, practical examples for man pages", "cli"),
    ("btop", "Beautiful resource monitor: CPU, memory, disk, network", "monitor"),
    ("htop", "Interactive process viewer", "monitor"),
    ("fastfetch", "System info in the terminal (neofetch successor)", "monitor"),
    ("direnv", "Loads environment variables per directory", "shell env"),
])
cask(C_TERM, [
    ("iterm2", "Advanced terminal for macOS", "terminal"),
    ("warp", "Modern terminal with AI and command blocks", "terminal"),
    ("ghostty", "Fast, native, GPU-accelerated terminal", "terminal"),
    ("wezterm", "Cross-platform terminal configured in Lua", "terminal"),
    ("kitty", "GPU-accelerated terminal", "terminal"),
    ("alacritty", "Minimalist, performance-focused terminal", "terminal"),
])

C_EDIT = "Editors & IDEs"
formula(C_EDIT, [
    ("neovim", "Modernized Vim, extensible with Lua", "editor vim"),
    ("helix", "Post-modern modal editor with built-in LSP", "editor"),
    ("micro", "Intuitive terminal editor with no learning curve", "editor"),
])
cask(C_EDIT, [
    ("visual-studio-code", "Extensible code editor from Microsoft", "editor web"),
    ("zed", "High-performance collaborative editor", "editor rust"),
    ("cursor", "Code editor with built-in AI", "editor ai"),
    ("sublime-text", "Fast and elegant editor", "editor"),
    ("jetbrains-toolbox", "Manager for JetBrains IDEs (IntelliJ, PyCharm…)", "ide java python"),
])

C_GIT = "Git & Version Control"
formula(C_GIT, [
    ("git", "Distributed version control system", "git"),
    ("gh", "GitHub in the terminal: PRs, issues and actions", "git github"),
    ("lazygit", "Simple terminal UI for git", "git"),
    ("git-delta", "Syntax-highlighting pager for git diffs", "git"),
    ("git-lfs", "Large file storage for git", "git"),
    ("pre-commit", "Framework for managing pre-commit hooks", "git python"),
    ("tig", "Text-mode interface for git repositories", "git"),
])
cask(C_GIT, [
    ("fork", "Fast and friendly git client", "git"),
    ("github", "GitHub Desktop", "git github"),
    ("gitkraken", "Cross-platform visual git client", "git"),
])

C_LANG = "Languages & Runtimes"
formula(C_LANG, [
    ("node", "JavaScript runtime (V8)", "node web javascript"),
    ("fnm", "Fast Node version manager (Rust)", "node rust"),
    ("pnpm", "Fast, disk-efficient Node package manager", "node web"),
    ("bun", "All-in-one JS runtime, bundler and package manager", "node web javascript"),
    ("deno", "Secure runtime for JavaScript and TypeScript", "web javascript"),
    ("python@3.12", "Python 3.12", "python"),
    ("pyenv", "Manage multiple Python versions", "python"),
    ("uv", "Extremely fast Python package and project manager", "python rust"),
    ("pipx", "Install Python apps in isolated environments", "python"),
    ("poetry", "Python dependency management and packaging", "python"),
    ("ruff", "Extremely fast Python linter and formatter", "python rust"),
    ("go", "Go programming language", "go"),
    ("rustup", "Rust toolchain installer and manager", "rust"),
    ("openjdk", "Java Development Kit (OpenJDK)", "java"),
    ("maven", "Java build and dependency management", "java"),
    ("gradle", "Build automation for JVM/Android", "java kotlin"),
    ("kotlin", "Kotlin programming language", "kotlin java"),
    ("ruby", "Ruby programming language", "ruby"),
    ("php", "PHP programming language", "php web"),
    ("composer", "PHP dependency manager", "php web"),
    ("zig", "Simple and robust systems language", "zig systems"),
    ("cmake", "Cross-platform C/C++ build system", "cpp systems"),
    ("llvm", "LLVM/Clang compilers and tools", "cpp systems"),
])

C_CONT = "Containers & Cloud"
formula(C_CONT, [
    ("docker", "Docker CLI (use with Colima or Docker Desktop)", "docker containers"),
    ("docker-compose", "Orchestrate multi-container applications", "docker containers"),
    ("colima", "Lightweight container runtime for macOS and Linux", "docker containers"),
    ("lazydocker", "Terminal UI for Docker", "docker containers"),
    ("dive", "Explore Docker image layers", "docker containers"),
    ("kubernetes-cli", "Kubernetes CLI (kubectl)", "k8s containers"),
    ("k9s", "Terminal UI for Kubernetes clusters", "k8s containers"),
    ("helm", "Kubernetes package manager", "k8s containers"),
    ("kubectx", "Quickly switch k8s contexts and namespaces", "k8s containers"),
    ("minikube", "Local Kubernetes for development", "k8s containers"),
    ("kind", "Kubernetes in Docker containers", "k8s containers docker"),
    ("opentofu", "Infrastructure as code (open Terraform fork)", "iac cloud"),
    ("ansible", "Automation and configuration management", "iac devops"),
    ("awscli", "Official AWS CLI", "cloud aws"),
])
cask(C_CONT, [
    ("docker-desktop", "Docker Desktop with GUI", "docker containers"),
    ("azure-cli", "Official Azure CLI", "cloud azure"),
    ("orbstack", "Fast, light containers and Linux VMs on Mac", "docker containers"),
    ("podman-desktop", "GUI for Podman and Kubernetes", "containers"),
    ("gcloud-cli", "Google Cloud CLI", "cloud gcp"),
])

C_DB = "Databases"
formula(C_DB, [
    ("postgresql@16", "PostgreSQL 16 relational database", "database sql"),
    ("mysql", "MySQL relational database", "database sql"),
    ("redis", "In-memory key-value store", "database cache"),
    ("sqlite", "Embedded SQL database", "database sql"),
    ("duckdb", "Embedded analytical database, great for data work", "database sql data"),
    ("mongosh", "Official MongoDB shell", "database nosql"),
    ("pgcli", "PostgreSQL client with autocomplete", "database sql python"),
    ("litecli", "SQLite client with autocomplete", "database sql python"),
])
cask(C_DB, [
    ("dbeaver-community", "Universal database client", "database sql"),
    ("tableplus", "Modern, native database client", "database sql"),
    ("pgadmin4", "PostgreSQL graphical administration", "database sql"),
    ("mongodb-compass", "Official MongoDB GUI", "database nosql"),
])

C_API = "APIs & Networking"
formula(C_API, [
    ("httpie", "User-friendly HTTP client for testing APIs", "api http"),
    ("xh", "Fast HTTP client inspired by HTTPie", "api http rust"),
    ("curlie", "curl with the HTTPie interface", "api http"),
    ("jq", "Command-line JSON processor", "json cli"),
    ("yq", "YAML/JSON/XML processor", "json cli yaml"),
    ("mkcert", "Locally trusted HTTPS certificates", "web http"),
    ("nmap", "Network and port scanner", "network security"),
    ("cloudflared", "Cloudflare tunnels to expose local services", "web network"),
    ("wget", "Download files over HTTP/FTP", "network cli"),
])
cask(C_API, [
    ("mitmproxy", "Proxy to inspect and modify HTTP(S) traffic", "api http security"),
    ("bruno", "Open-source, offline-first API client", "api http"),
    ("postman", "Platform to build and test APIs", "api http"),
    ("insomnia", "REST/GraphQL/gRPC client", "api http"),
    ("ngrok", "Secure tunnels to localhost", "web network"),
    ("wireshark-app", "Network packet analyzer", "network security"),
])

C_UTIL = "Dev Utilities"
formula(C_UTIL, [
    ("tree", "List directories as a tree", "cli"),
    ("watch", "Run a command periodically", "cli"),
    ("hyperfine", "Command-line benchmarking tool", "cli rust"),
    ("tokei", "Count lines of code by language", "cli rust"),
    ("just", "Project command runner (a make alternative)", "cli rust"),
    ("shellcheck", "Static analysis for shell scripts", "shell lint"),
    ("shfmt", "Shell script formatter", "shell lint"),
    ("hadolint", "Dockerfile linter", "docker lint"),
    ("act", "Run GitHub Actions locally", "git github ci"),
    ("gnupg", "GPG: encryption and signatures", "security"),
    ("age", "Simple, modern file encryption", "security"),
    ("ffmpeg", "Convert and process audio and video", "media"),
    ("imagemagick", "Image manipulation from the CLI", "media"),
    ("pandoc", "Universal document converter", "docs"),
    ("graphviz", "Generate diagrams from text", "docs"),
])
cask(C_UTIL, [
    ("rectangle", "Window manager driven by shortcuts", "productivity"),
    ("raycast", "Extensible launcher with snippets and automations", "productivity"),
    ("obsidian", "Markdown notes with links between documents", "productivity docs"),
    ("figma", "Collaborative interface design", "design web"),
    ("1password-cli", "1Password in the terminal", "security"),
])

C_FONT = "Fonts"
cask(C_FONT, [
    ("font-jetbrains-mono-nerd-font", "JetBrains Mono with Nerd Font icons", "font terminal"),
    ("font-fira-code-nerd-font", "Fira Code with ligatures and icons", "font terminal"),
    ("font-meslo-lg-nerd-font", "Meslo LG, recommended for Powerlevel10k/Starship", "font terminal"),
], profiles=(DEV, GAMER))

# ───────────────────────── GAMER ─────────────────────────
G = (GAMER,)
C_STORE = "Stores & Launchers"
cask(C_STORE, [
    ("steam", "Valve's game store and library", "game store"),
    ("epic-games", "Epic Games store and Fortnite", "game store"),
    ("gog-galaxy", "GOG launcher, DRM-free games", "game store"),
    ("battle-net", "Blizzard launcher", "game store"),
    ("heroic", "Open-source launcher for Epic, GOG and Amazon Games", "game store"),
    ("itch", "itch.io app for indie games", "game store indie"),
    ("prismlauncher", "Minecraft launcher with multiple instances and mods", "game minecraft mods"),
    ("minecraft", "Official Minecraft launcher", "game minecraft"),
    ("steamcmd", "Steam command-line client (dedicated servers)", "game steam server"),
], profiles=G)
C_COMP = "Compatibility (Windows)"
cask(C_COMP, [
    ("crossover", "Run Windows apps and games on Mac (commercial Wine)", "game wine"),
    ("whisky", "Wine wrapper to run Windows games on Mac (archived project)", "game wine"),
    ("wine-stable", "Windows compatibility layer (stable Wine)", "game wine"),
], profiles=G)
formula(C_COMP, [
    ("winetricks", "Install libraries and tweaks for Wine", "game wine"),
], profiles=G)

C_EMU = "Emulators"
cask(C_EMU, [
    ("retroarch", "Unified frontend for hundreds of consoles (libretro)", "game retro emulator"),
    ("openemu", "Multi-system emulation with a native Mac interface", "game retro emulator"),
    ("dolphin", "GameCube and Wii emulator", "game retro emulator"),
    ("pcsx2", "PlayStation 2 emulator", "game retro emulator"),
    ("ppsspp-emulator", "PSP emulator", "game retro emulator"),
    ("mgba-app", "Game Boy Advance emulator", "game retro emulator"),
    ("melonds", "Nintendo DS emulator", "game retro emulator"),
    ("cemu", "Wii U emulator", "game retro emulator"),
    ("flycast", "Dreamcast emulator", "game retro emulator"),
], profiles=G)
formula(C_EMU, [
    ("mame", "Arcade and classic systems emulator", "game retro emulator"),
    ("scummvm", "Play classic adventure games (Monkey Island etc.)", "game retro"),
    ("dosbox-staging", "Modernized DOSBox for MS-DOS games", "game retro"),
    ("mednafen", "Command-line multi-system emulator", "game retro emulator"),
    ("stella", "Atari 2600 emulator", "game retro emulator"),
], profiles=G)

C_STREAM = "Streaming & Communication"
cask(C_STREAM, [
    ("discord", "Voice and text chat for gaming communities", "game social"),
    ("obs", "Recording and live streaming", "streaming media"),
    ("moonlight", "Stream games from your PC (NVIDIA/Sunshine)", "game streaming"),
    ("parsec", "Remote play with low latency", "game streaming"),
    ("vlc", "Media player that plays everything", "media"),
    ("spotify", "Music for gaming and coding", "media"),
    ("handbrake-app", "Video conversion for clips and gameplay", "media"),
    ("elgato-stream-deck", "Stream Deck software", "streaming"),
], profiles=G)
formula(C_STREAM, [
    ("yt-dlp", "Download videos from YouTube and other sites", "media cli"),
    ("streamlink", "Watch streams (Twitch etc.) in the player you prefer", "streaming media"),
], profiles=G)

C_ENG = "Engines & Game Creation"
cask(C_ENG, [
    ("godot", "Open-source 2D/3D game engine", "gamedev engine"),
    ("unity-hub", "Unity Editor manager", "gamedev engine"),
    ("blender", "3D modeling, animation and rendering", "gamedev 3d"),
    ("tiled", "2D tile map editor", "gamedev 2d"),
    ("krita", "Digital painting and pixel art", "gamedev art"),
    ("audacity", "Audio editor", "gamedev audio"),
], profiles=(GAMER, DEV))
formula(C_ENG, [
    ("sdl3", "SDL 3 multimedia library", "gamedev cpp"),
    ("raylib", "Simple library for programming games in C", "gamedev cpp"),
], profiles=(GAMER, DEV))

C_PERF = "Performance & Peripherals"
cask(C_PERF, [
    ("stats", "CPU/GPU/temperature monitor in the menu bar", "monitor"),
    ("macs-fan-control", "Fan control for Macs", "monitor"),
    ("geekbench", "CPU and GPU benchmark", "monitor benchmark"),
    ("linearmouse", "Customize mouse acceleration and scrolling", "peripheral"),
    ("karabiner-elements", "Advanced keyboard remapping", "peripheral"),
    ("betterdisplay", "Display resolution and HiDPI control", "peripheral display"),
], profiles=G)
formula(C_PERF, [
    ("btop", "Beautiful resource monitor", "monitor"),
    ("fastfetch", "System info to show off your setup", "monitor"),
    ("nvtop", "GPU monitor (NVIDIA/AMD/Intel)", "monitor gpu"),
    ("glances", "Full system monitoring", "monitor"),
    ("cmatrix", "The Matrix code rain in your terminal", "fun"),
], profiles=G, platforms=BOTH)

# ───────────────────────── KITS ─────────────────────────
KITS: List[Kit] = [
    Kit("Supercharged Terminal", "Modern, productive shell for everyday work", DEV,
        ("formula:starship", "formula:fzf", "formula:zoxide", "formula:ripgrep",
         "formula:fd", "formula:bat", "formula:eza", "formula:tmux",
         "formula:zsh-autosuggestions", "formula:zsh-syntax-highlighting")),
    Kit("Web Full-Stack", "Node, databases, API client and editor", DEV,
        ("formula:git", "formula:gh", "formula:node", "formula:pnpm", "formula:postgresql@16",
         "formula:redis", "formula:httpie", "formula:jq", "cask:visual-studio-code",
         "cask:bruno")),
    Kit("Python & Data", "Modern Python environment with data analysis", DEV,
        ("formula:python@3.12", "formula:uv", "formula:pyenv", "formula:ruff",
         "formula:pipx", "formula:duckdb", "formula:sqlite", "formula:jq")),
    Kit("DevOps & Cloud", "Containers, Kubernetes and infrastructure as code", DEV,
        ("formula:docker", "formula:docker-compose", "formula:colima", "formula:kubernetes-cli",
         "formula:k9s", "formula:helm", "formula:opentofu", "formula:awscli",
         "formula:ansible", "formula:lazydocker")),
    Kit("Git Pro", "A comfortable git workflow in the terminal", DEV,
        ("formula:git", "formula:gh", "formula:lazygit", "formula:git-delta",
         "formula:git-lfs", "formula:pre-commit")),
    Kit("Gaming Mac", "Stores, voice chat and streaming to start playing", GAMER,
        ("cask:steam", "cask:epic-games", "cask:heroic", "cask:discord", "cask:obs",
         "cask:stats")),
    Kit("Retro Gaming", "Emulators for classics from many consoles", GAMER,
        ("cask:retroarch", "cask:openemu", "cask:dolphin", "cask:ppsspp-emulator",
         "cask:mgba-app", "formula:scummvm", "formula:dosbox-staging")),
    Kit("Windows Games on Mac", "Compatibility layers to run Windows games", GAMER,
        ("cask:crossover", "cask:whisky", "formula:winetricks", "cask:steam")),
    Kit("Streamer", "Capture, broadcast and edit your gameplay", GAMER,
        ("cask:obs", "cask:elgato-stream-deck", "cask:handbrake-app", "formula:ffmpeg",
         "formula:streamlink", "cask:audacity")),
    Kit("Indie Game Dev", "Engine, art and audio to build your game", GAMER,
        ("cask:godot", "cask:blender", "cask:krita", "cask:tiled", "cask:audacity")),
    Kit("Terminal for Gamers (Linux/Mac)", "Monitoring and fun without leaving the terminal", GAMER,
        ("formula:btop", "formula:fastfetch", "formula:nvtop", "formula:cmatrix",
         "formula:yt-dlp", "formula:mame")),
]

CATEGORIES_DEV = [C_TERM, C_EDIT, C_GIT, C_LANG, C_CONT, C_DB, C_API, C_UTIL, C_FONT]
CATEGORIES_GAMER = [C_STORE, C_COMP, C_EMU, C_STREAM, C_ENG, C_PERF]
ALL_CATEGORIES = CATEGORIES_DEV + CATEGORIES_GAMER

BY_KEY = {i.key: i for i in ITEMS}

# Baseline picks suggested when nothing relevant is installed yet.
ESSENTIALS = {
    DEV: ["formula:git", "formula:ripgrep", "formula:fzf", "formula:jq", "cask:visual-studio-code",
          "formula:starship", "formula:gh", "formula:btop"],
    GAMER: ["cask:steam", "cask:discord", "cask:obs", "cask:heroic", "cask:retroarch",
            "formula:btop", "cask:stats", "cask:vlc"],
}
