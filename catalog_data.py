"""Curated catalog of Homebrew packages for developers and gamers.

Formulae work on macOS and Linux; casks (GUI apps) are macOS only.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple

DEV = "dev"
GAMER = "gamer"
SRE = "sre"
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
    tap: str = ""  # e.g. "hashicorp/tap" for formulae outside homebrew-core

    @property
    def full_name(self) -> str:
        return f"{self.tap}/{self.name}" if self.tap else self.name

    @property
    def key(self) -> str:
        return f"{self.kind}:{self.name}"

    @property
    def install_cmd(self) -> List[str]:
        cmd = ["install"]
        if self.kind == "cask":
            cmd.append("--cask")
        return cmd + [self.full_name]


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

# ───────────────────── SRE / DevOps / Cloud ─────────────────────
S = (SRE,)
HT = "hashicorp/tap"
C_CLOUD = "Cloud CLIs"
formula(C_CLOUD, [
    ("awscli", "Official AWS CLI", "cloud aws"),
    ("aws-sam-cli", "AWS Serverless Application Model CLI", "cloud aws serverless"),
    ("aws-vault", "Securely store and use AWS credentials", "cloud aws security"),
    ("aws-iam-authenticator", "Authenticate to Kubernetes (EKS) with AWS IAM", "cloud aws k8s"),
    ("aws-cdk", "AWS Cloud Development Kit", "cloud aws iac"),
    ("eksctl", "Create and manage Amazon EKS clusters", "cloud aws k8s"),
    ("oci-cli", "Oracle Cloud Infrastructure CLI", "cloud oracle"),
    ("doctl", "DigitalOcean CLI", "cloud digitalocean"),
    ("supabase", "Supabase CLI: local dev and migrations", "cloud database"),
    ("firebase-cli", "Firebase CLI", "cloud gcp"),
], profiles=(SRE, DEV))
cask(C_CLOUD, [
    ("azure-cli", "Official Azure CLI", "cloud azure"),
    ("gcloud-cli", "Google Cloud CLI (gcloud)", "cloud gcp"),
    ("session-manager-plugin", "AWS Session Manager plugin for the AWS CLI", "cloud aws"),
], profiles=(SRE, DEV))

C_PAAS = "Platforms (PaaS)"
formula(C_PAAS, [
    ("railway", "Railway CLI: deploy and manage projects", "paas railway"),
    ("flyctl", "Fly.io CLI", "paas fly"),
    ("heroku", "Heroku CLI", "paas heroku"),
    ("netlify-cli", "Netlify CLI", "paas web"),
    ("render", "Render CLI", "paas"),
], profiles=(SRE, DEV))

C_IAC = "Infrastructure as Code"
formula(C_IAC, [
    ("terraform", "Terraform (from the HashiCorp tap)", "iac terraform cloud"),
    ("packer", "Build machine images (HashiCorp tap)", "iac hashicorp"),
    ("vault", "Secrets management (HashiCorp tap)", "iac hashicorp security"),
    ("consul", "Service discovery and mesh (HashiCorp tap)", "iac hashicorp"),
    ("nomad", "Workload orchestrator (HashiCorp tap)", "iac hashicorp"),
], profiles=S)
for _it in ITEMS[-5:]:
    ITEMS[ITEMS.index(_it)] = Item(_it.name, _it.kind, _it.category, _it.desc, _it.profiles,
                                   _it.platforms, _it.tags, HT)
formula(C_IAC, [
    ("opentofu", "Open-source Terraform fork", "iac terraform cloud"),
    ("tenv", "Version manager for Terraform, OpenTofu and Terragrunt", "iac terraform"),
    ("terragrunt", "Thin wrapper to keep Terraform configs DRY", "iac terraform"),
    ("terraform-docs", "Generate docs from Terraform modules", "iac terraform docs"),
    ("terraform-ls", "Terraform language server", "iac terraform editor"),
    ("checkov", "Static analysis for IaC security and compliance", "iac security lint"),
    ("infracost", "Cloud cost estimates for Terraform", "iac terraform finops"),
    ("pulumi", "IaC in real programming languages", "iac cloud"),
    ("ansible-lint", "Best-practices linter for Ansible", "iac devops lint"),
], profiles=S)

C_K8S = "Kubernetes Toolbox"
formula(C_K8S, [
    ("kustomize", "Customize Kubernetes manifests without templates", "k8s containers"),
    ("stern", "Tail logs from multiple pods", "k8s containers"),
    ("kubeseal", "Sealed Secrets CLI", "k8s security"),
    ("argocd", "Argo CD CLI for GitOps", "k8s gitops"),
    ("flux", "Flux CD CLI for GitOps", "k8s gitops"),
    ("kubeconform", "Fast Kubernetes manifest validator", "k8s lint"),
    ("skaffold", "Continuous development for Kubernetes", "k8s containers"),
    ("istioctl", "Istio service mesh CLI", "k8s mesh"),
    ("linkerd", "Linkerd service mesh CLI", "k8s mesh"),
    ("velero", "Back up and restore cluster resources", "k8s backup"),
    ("krew", "Plugin manager for kubectl", "k8s containers"),
    ("popeye", "Scan clusters for misconfigurations", "k8s lint"),
    ("k3d", "Run k3s Kubernetes clusters in Docker", "k8s containers docker"),
    ("kubie", "Isolated kubectl contexts per shell", "k8s containers"),
    ("kubernetes-cli", "Kubernetes CLI (kubectl)", "k8s containers"),
    ("helm", "Kubernetes package manager", "k8s containers"),
    ("k9s", "Terminal UI for Kubernetes clusters", "k8s containers"),
    ("kubectx", "Switch k8s contexts and namespaces quickly", "k8s containers"),
], profiles=S)
cask(C_K8S, [("lens", "Kubernetes IDE", "k8s containers")], profiles=S)

C_OBS = "Observability & Reliability"
formula(C_OBS, [
    ("prometheus", "Monitoring system and time-series database", "monitor observability"),
    ("grafana", "Dashboards and visualization", "monitor observability"),
    ("k6", "Modern load testing tool", "loadtest sre"),
    ("hey", "HTTP load generator", "loadtest sre"),
    ("wrk", "HTTP benchmarking tool", "loadtest sre"),
    ("vegeta", "HTTP load testing tool and library", "loadtest sre"),
    ("trivy", "Vulnerability scanner for images, IaC and repos", "security containers"),
    ("grype", "Container and filesystem vulnerability scanner", "security containers"),
    ("syft", "Generate SBOMs from images and filesystems", "security containers"),
    ("cosign", "Sign and verify container images", "security containers"),
    ("gitleaks", "Detect secrets in git repos", "security git"),
    ("sops", "Encrypted secrets files (YAML/JSON/ENV)", "security iac"),
    ("step", "Zero-trust PKI and certificates toolkit", "security"),
    ("mtr", "Traceroute and ping combined", "network sre"),
    ("iperf3", "Network throughput testing", "network sre"),
    ("bandwhich", "Per-process network bandwidth monitor", "network sre rust"),
    ("doggo", "Friendly DNS client", "network sre"),
    ("ctop", "Top-like container metrics", "containers monitor"),
    ("duf", "Better df: disk usage overview", "monitor cli"),
    ("gdu", "Fast disk usage analyzer", "monitor cli"),
    ("btop", "Beautiful resource monitor", "monitor"),
    ("jq", "Command-line JSON processor", "json cli"),
    ("yq", "YAML/JSON/XML processor", "json cli yaml"),
    ("nmap", "Network and port scanner", "network security"),
], profiles=S)
cask(C_OBS, [("datadog-agent", "Datadog Agent for macOS", "monitor observability")], profiles=S)

# ───────────────────── More languages ─────────────────────
C_NODE = "Node.js & TypeScript"
formula(C_NODE, [
    ("typescript", "TypeScript compiler", "node web typescript"),
    ("yarn", "Yarn package manager", "node web"),
    ("nvm", "Node version manager", "node"),
    ("eslint", "JavaScript/TypeScript linter", "node web lint"),
    ("prettier", "Opinionated code formatter", "node web lint"),
])

C_GO = "Go"
formula(C_GO, [
    ("gopls", "Official Go language server", "go editor"),
    ("golangci-lint", "Fast Go linters runner", "go lint"),
    ("delve", "Go debugger", "go debug"),
    ("goreleaser", "Release automation for Go", "go ci"),
    ("air", "Live reload for Go apps", "go"),
    ("gofumpt", "Stricter gofmt", "go lint"),
    ("staticcheck", "Advanced Go static analysis", "go lint"),
    ("gotestsum", "Better go test output", "go test"),
    ("mockery", "Mock code generator for Go interfaces", "go test"),
])

C_NET = ".NET"
formula(C_NET, [
    ("dotnet", "Microsoft .NET SDK (latest)", "dotnet csharp"),
    ("dotnet@8", ".NET 8 SDK (LTS)", "dotnet csharp"),
    ("powershell", "PowerShell shell and scripting language", "dotnet shell"),
    ("nuget", "NuGet package manager CLI", "dotnet csharp"),
])
cask(C_NET, [("dotnet-sdk", ".NET SDK installer package", "dotnet csharp")])

C_JAVA = "Java & JVM"
formula(C_JAVA, [
    ("openjdk@21", "OpenJDK 21 (LTS)", "java"),
    ("openjdk@17", "OpenJDK 17 (LTS)", "java"),
    ("openjdk@11", "OpenJDK 11", "java"),
    ("jenv", "Manage multiple Java versions", "java"),
    ("sbt", "Scala build tool", "java scala"),
    ("scala", "Scala programming language", "java scala"),
    ("jbang", "Run Java as scripts", "java"),
    ("tomcat", "Apache Tomcat servlet container", "java web"),
    ("jdtls", "Eclipse JDT language server for Java", "java editor"),
])
cask(C_JAVA, [("visualvm", "Java profiler and monitor", "java monitor")])

C_SHELL = "Shell & Unix"
formula(C_SHELL, [
    ("bash", "Bash 5 (newer than the macOS default)", "shell unix"),
    ("zsh", "Z shell", "shell unix"),
    ("fish", "Friendly interactive shell", "shell unix"),
    ("nushell", "Shell that treats data as structured tables", "shell unix rust"),
    ("bats-core", "Bash automated testing system", "shell test"),
    ("coreutils", "GNU core utilities (ls, cp, sort…)", "unix"),
    ("findutils", "GNU find, xargs, locate", "unix"),
    ("gnu-sed", "GNU sed", "unix"),
    ("gawk", "GNU awk", "unix"),
    ("grep", "GNU grep", "unix"),
    ("gnu-tar", "GNU tar", "unix"),
    ("util-linux", "Linux utilities (column, getopt…)", "unix"),
    ("moreutils", "Extra Unix tools (sponge, ts, vipe…)", "unix"),
    ("parallel", "Run shell commands in parallel", "unix"),
    ("rsync", "Fast, versatile file copying", "unix"),
    ("screen", "Classic terminal multiplexer", "unix terminal"),
    ("lsof", "List open files", "unix"),
    ("pv", "Monitor data through a pipe", "unix"),
    ("entr", "Run commands when files change", "unix"),
    ("ncdu", "Disk usage analyzer (ncurses)", "unix monitor"),
    ("bash-completion@2", "Programmable completion for Bash 4.2+", "shell unix"),
    ("shellcheck", "Static analysis for shell scripts", "shell lint"),
    ("shfmt", "Shell script formatter", "shell lint"),
])

C_MAIN = "Mainframe & Legacy"
formula(C_MAIN, [
    ("x3270", "IBM 3270 terminal emulator (X11)", "mainframe tn3270"),
    ("hercules", "System/370, ESA/390 and z/Architecture emulator", "mainframe emulator"),
    ("gnucobol", "GnuCOBOL compiler for COBOL", "mainframe cobol"),
], platforms=BOTH)

# ───────────────────── Extra kits ─────────────────────
KITS.extend([
    Kit("Terraform + AWS", "IaC with Terraform, AWS tooling and security scanners", SRE,
        ("formula:terraform", "formula:tenv", "formula:terraform-docs",
         "formula:checkov", "formula:infracost", "formula:awscli", "formula:aws-vault",
         "cask:session-manager-plugin", "formula:aws-sam-cli")),
    Kit("Google Cloud", "gcloud and Firebase for GCP work", SRE,
        ("cask:gcloud-cli", "formula:firebase-cli", "formula:opentofu", "formula:kubernetes-cli",
         "formula:k9s")),
    Kit("Azure", "Azure CLI plus IaC and Kubernetes basics", SRE,
        ("cask:azure-cli", "formula:opentofu", "formula:kubernetes-cli", "formula:helm",
         "formula:k9s", "formula:powershell")),
    Kit("Railway & PaaS", "Deploy fast: Railway, Fly.io, Heroku and Netlify CLIs", SRE,
        ("formula:railway", "formula:flyctl", "formula:heroku", "formula:netlify-cli",
         "formula:doctl")),
    Kit("SRE Toolkit", "Debugging, load testing, networking and incident basics", SRE,
        ("formula:k9s", "formula:stern", "formula:k6", "formula:mtr", "formula:doggo",
         "formula:bandwhich", "formula:btop", "formula:jq", "formula:yq", "formula:duf",
         "formula:gdu")),
    Kit("Kubernetes Admin", "Day-2 Kubernetes tooling and GitOps", SRE,
        ("formula:kubernetes-cli", "formula:helm", "formula:kustomize", "formula:k9s",
         "formula:kubectx", "formula:stern", "formula:argocd", "formula:flux", "formula:kubeconform",
         "formula:krew")),
    Kit("DevSecOps", "Scan images, IaC and secrets in your pipeline", SRE,
        ("formula:trivy", "formula:grype", "formula:syft", "formula:cosign", "formula:gitleaks",
         "formula:checkov", "formula:sops")),
    Kit("Node.js & TypeScript", "Node runtime, package managers and linting", DEV,
        ("formula:node", "formula:fnm", "formula:pnpm", "formula:yarn", "formula:typescript",
         "formula:eslint", "formula:prettier")),
    Kit("Go Developer", "Go toolchain with LSP, linting and debugging", DEV,
        ("formula:go", "formula:gopls", "formula:golangci-lint", "formula:delve",
         "formula:goreleaser", "formula:air", "formula:gotestsum")),
    Kit(".NET Developer", ".NET SDK, PowerShell and NuGet", DEV,
        ("formula:dotnet", "formula:powershell", "formula:nuget", "cask:visual-studio-code",
         "cask:azure-cli")),
    Kit("Java Developer", "JDKs, build tools and tooling", DEV,
        ("formula:openjdk@21", "formula:openjdk@17", "formula:jenv", "formula:maven",
         "formula:gradle", "formula:jbang", "cask:visualvm")),
    Kit("Shell & Unix Power User", "GNU tools, shells and scripting helpers", DEV,
        ("formula:bash", "formula:coreutils", "formula:findutils", "formula:gnu-sed", "formula:gawk",
         "formula:grep", "formula:parallel", "formula:moreutils", "formula:shellcheck",
         "formula:shfmt", "formula:bats-core")),
    Kit("Mainframe & COBOL", "3270 emulator, Hercules and GnuCOBOL", DEV,
        ("formula:x3270", "formula:hercules", "formula:gnucobol")),
    Kit("Game Developer", "Engines, art and libraries for building games", DEV,
        ("cask:godot", "cask:unity-hub", "cask:blender", "cask:tiled", "cask:krita",
         "formula:raylib", "formula:sdl3")),
])

# Merge duplicate keys (same package listed in several areas): keep the first, union profiles/tags.
_merged: dict = {}
for _it in ITEMS:
    if _it.key in _merged:
        _o = _merged[_it.key]
        _merged[_it.key] = Item(_o.name, _o.kind, _o.category, _o.desc,
                                tuple(dict.fromkeys(_o.profiles + _it.profiles)), _o.platforms,
                                tuple(dict.fromkeys(_o.tags + _it.tags)), _o.tap or _it.tap)
    else:
        _merged[_it.key] = _it
ITEMS[:] = list(_merged.values())

# Existing Dev tooling is also useful for SRE/Cloud profiles.
for _i, _it in enumerate(ITEMS):
    if _it.category in (C_CONT, C_API) and SRE not in _it.profiles:
        ITEMS[_i] = Item(_it.name, _it.kind, _it.category, _it.desc, _it.profiles + (SRE,),
                         _it.platforms, _it.tags, _it.tap)

CATEGORIES_DEV = [C_TERM, C_EDIT, C_GIT, C_LANG, C_NODE, C_GO, C_NET, C_JAVA, C_SHELL, C_MAIN,
                  C_CONT, C_DB, C_API, C_UTIL, C_FONT]
CATEGORIES_SRE = [C_CLOUD, C_IAC, C_K8S, C_CONT, C_PAAS, C_OBS, C_API]
CATEGORIES_GAMER = [C_STORE, C_COMP, C_EMU, C_STREAM, C_ENG, C_PERF]
ALL_CATEGORIES = list(dict.fromkeys(CATEGORIES_DEV + CATEGORIES_SRE + CATEGORIES_GAMER))

BY_KEY = {i.key: i for i in ITEMS}

# Baseline picks suggested when nothing relevant is installed yet.
ESSENTIALS = {
    DEV: ["formula:git", "formula:ripgrep", "formula:fzf", "formula:jq", "cask:visual-studio-code",
          "formula:starship", "formula:gh", "formula:btop"],
    SRE: ["formula:kubernetes-cli", "formula:k9s", "formula:terraform", "formula:awscli",
          "cask:gcloud-cli", "cask:azure-cli", "formula:helm", "formula:jq", "formula:trivy"],
    GAMER: ["cask:steam", "cask:discord", "cask:obs", "cask:heroic", "cask:retroarch",
            "formula:btop", "cask:stats", "cask:vlc"],
}
