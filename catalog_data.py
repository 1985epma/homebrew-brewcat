"""Curated catalog of Homebrew packages for developers and gamers.

Formulae work on macOS and Linux; casks (GUI apps) are macOS only.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace as _dc_replace
from typing import List, Optional, Tuple

DEV = "dev"
GAMER = "gamer"
SRE = "sre"
QA = "qa"
OFFICE = "office"
DESIGN = "design"
DJ = "dj"
DS = "datascience"
DE = "dataeng"
NET = "network"
SEC = "security"
VENDOR = "vendors"
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
    groups: Tuple[str, ...] = ()  # extra categories this package also appears in

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
    ("tlrc", "Short, practical examples for man pages (tldr client)", "cli"),
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
], profiles=G)
formula(C_COMP, [
    ("winetricks", "Install libraries and tweaks for Wine", "game wine"),
], profiles=G)

C_EMU = "Emulators"
cask(C_EMU, [
    ("retroarch", "Unified frontend for hundreds of consoles (libretro)", "game retro emulator"),
    ("dolphin", "GameCube and Wii emulator", "game retro emulator"),
    ("pcsx2", "PlayStation 2 emulator", "game retro emulator"),
    ("ppsspp-emulator", "PSP emulator", "game retro emulator"),
    ("mgba-app", "Game Boy Advance emulator", "game retro emulator"),
    ("cemu", "Wii U emulator", "game retro emulator"),
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
        ("cask:retroarch", "cask:dolphin", "cask:ppsspp-emulator",
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

# ───────────────────── More professional profiles ─────────────────────
# QA
C_QA_AUTO = "Test Automation"
formula(C_QA_AUTO, [
    ("selenium-server", "Selenium Server / Grid for browser automation", "qa selenium"),
    ("geckodriver", "WebDriver proxy for Firefox", "qa selenium"),
    ("appium", "Mobile app automation (iOS/Android)", "qa mobile"),
    ("newman", "Run Postman collections from the CLI", "qa api"),
    ("hurl", "Run and test HTTP requests defined in plain text", "qa api http"),
    ("pytest", "Python testing framework", "qa python"),
    ("robot-framework", "Generic keyword-driven test automation framework", "qa python"),
    ("lighthouse", "Audit performance, accessibility and SEO", "qa web"),
    ("sonar-scanner", "SonarQube/SonarCloud code quality scanner", "qa lint"),
], profiles=(QA,))
cask(C_QA_AUTO, [
    ("maestro", "Simple UI testing for mobile and web", "qa mobile"),
    ("android-studio", "Android IDE and emulators", "qa mobile"),
    ("google-chrome", "Chrome browser for testing", "qa web"),
    ("firefox", "Firefox browser for testing", "qa web"),
    ("responsively", "Preview a site on many device sizes at once", "qa web design"),
    ("browserstacklocal", "BrowserStack Local testing tunnel", "qa web"),
], profiles=(QA,))
C_QA_PERF = "Load & API Testing"
formula(C_QA_PERF, [
    ("k6", "Modern load testing tool", "qa loadtest sre"),
    ("jmeter", "Apache JMeter load and functional testing", "qa loadtest"),
    ("locust", "Scalable load testing in Python", "qa loadtest python"),
    ("allure", "Test report framework", "qa report"),
    ("httpie", "User-friendly HTTP client for testing APIs", "api http"),
], profiles=(QA,))
cask(C_QA_PERF, [
    ("postman", "Platform to build and test APIs", "api http"),
    ("bruno", "Open-source, offline-first API client", "api http"),
    ("insomnia", "REST/GraphQL/gRPC client", "api http"),
    ("charles", "HTTP proxy and monitor", "qa api http"),
    ("mitmproxy", "Inspect and modify HTTP(S) traffic", "api http security"),
], profiles=(QA,))

# Office
C_OFFICE = "Office & Productivity"
cask(C_OFFICE, [
    ("libreoffice", "Full open-source office suite", "office docs"),
    ("onlyoffice", "Office suite compatible with Microsoft formats", "office docs"),
    ("microsoft-office", "Microsoft 365 apps (Word, Excel, PowerPoint)", "office docs"),
    ("notion", "Notes, docs and databases in one place", "office notes"),
    ("obsidian", "Markdown notes with links between documents", "office notes"),
    ("zotero", "Reference manager for research", "office research"),
    ("xmind", "Mind mapping", "office notes"),
    ("drawio", "Diagrams and flowcharts", "office diagrams"),
    ("calibre", "E-book manager and converter", "office docs"),
    ("typora", "Minimal Markdown editor", "office docs"),
    ("thunderbird", "Email client", "office mail"),
    ("raycast", "Extensible launcher with snippets and automations", "productivity"),
    ("alfred", "Launcher and workflow automation", "productivity"),
    ("rectangle", "Window manager driven by shortcuts", "productivity"),
    ("maccy", "Lightweight clipboard history", "productivity"),
    ("numi", "Calculator that understands text", "productivity"),
    ("keka", "Archive manager (zip, 7z, rar…)", "productivity"),
    ("the-unarchiver", "Open almost any archive format", "productivity"),
    ("skim", "PDF reader and note-taker", "office pdf"),
    ("pdfsam-basic", "Split, merge and rotate PDFs", "office pdf"),
], profiles=(OFFICE,))
cask("Communication & Cloud Drive", [
    ("slack", "Team messaging", "office chat"),
    ("zoom", "Video meetings", "office chat"),
    ("microsoft-teams", "Microsoft Teams", "office chat"),
    ("telegram", "Telegram messenger", "office chat"),
    ("whatsapp", "WhatsApp Desktop", "office chat"),
    ("signal", "Private messenger", "office chat security"),
    ("google-drive", "Google Drive for desktop", "office cloud"),
    ("dropbox", "Dropbox sync", "office cloud"),
    ("bitwarden", "Password manager", "office security"),
], profiles=(OFFICE,))
formula("Documents & PDF Tools", [
    ("pandoc", "Universal document converter", "docs"),
    ("ghostscript", "PostScript and PDF interpreter", "office pdf"),
    ("poppler", "PDF rendering tools (pdftotext…)", "office pdf"),
    ("qpdf", "Transform and inspect PDFs", "office pdf"),
    ("tesseract", "OCR engine", "office ocr"),
    ("ocrmypdf", "Add an OCR text layer to scanned PDFs", "office ocr pdf"),
], profiles=(OFFICE,))

# Design
C_DWEB = "Web & UI Design"
cask(C_DWEB, [
    ("figma", "Collaborative interface design", "design web"),
    ("sketch", "Digital design toolkit for Mac", "design web"),
    ("lunacy", "Free Sketch-compatible design tool", "design web"),
    ("zeplin", "Design handoff for developers", "design web"),
    ("polypane", "Browser for web developers and designers", "design web"),
    ("responsively", "Preview a site on many device sizes at once", "design web qa"),
    ("colorsnapper", "Color picker for the menu bar", "design web"),
    ("imageoptim", "Optimize images for the web", "design web"),
    ("font-inter", "Inter typeface", "design font"),
    ("font-roboto", "Roboto typeface", "design font"),
    ("font-montserrat", "Montserrat typeface", "design font"),
    ("font-poppins", "Poppins typeface", "design font"),
    ("font-fira-sans", "Fira Sans typeface", "design font"),
], profiles=(DESIGN,))
formula(C_DWEB, [
    ("svgo", "Optimize SVG files", "design web"),
    ("webp", "WebP image tools (cwebp, dwebp)", "design web"),
    ("pngquant", "Lossy PNG compressor", "design web"),
    ("optipng", "Lossless PNG optimizer", "design web"),
    ("jpegoptim", "JPEG optimizer", "design web"),
    ("mozjpeg", "Better JPEG encoder", "design web"),
    ("librsvg", "SVG rendering library and rsvg-convert", "design web"),
], profiles=(DESIGN,))
C_DGFX = "Graphics & Photo"
cask(C_DGFX, [
    ("inkscape", "Vector graphics editor", "design graphics"),
    ("gimp", "Raster image editor", "design graphics"),
    ("krita", "Digital painting and illustration", "design graphics"),
    ("affinity", "Affinity Designer, Photo and Publisher", "design graphics"),
    ("rawtherapee", "RAW photo processing", "design photo"),
    ("scribus", "Desktop publishing and page layout", "design print"),
    ("xnviewmp", "Image viewer and batch converter", "design graphics"),
    ("blender", "3D modeling, animation and rendering", "design 3d"),
], profiles=(DESIGN,))
formula(C_DGFX, [
    ("imagemagick", "Image manipulation from the CLI", "media design"),
    ("graphicsmagick", "Fast image processing toolkit", "media design"),
    ("vips", "Very fast image processing", "media design"),
    ("exiftool", "Read and write image metadata", "media design"),
    ("potrace", "Trace bitmaps into vector graphics", "design graphics"),
], profiles=(DESIGN,))
C_DVID = "Video & Motion"
cask(C_DVID, [
    ("obs", "Recording and live streaming", "video streaming"),
    ("kdenlive", "Open-source video editor", "video"),
    ("shotcut", "Cross-platform video editor", "video"),
    ("openshot-video-editor", "Easy-to-use video editor", "video"),
    ("handbrake-app", "Video transcoder", "video"),
    ("losslesscut", "Lossless video/audio trimming", "video"),
    ("iina", "Modern media player for macOS", "video"),
    ("vlc", "Media player that plays everything", "video"),
    ("mediainfo", "Technical info about media files", "video"),
    ("audacity", "Audio editor", "audio"),
], profiles=(DESIGN,))
formula(C_DVID, [
    ("ffmpeg", "Convert and process audio and video", "video media"),
    ("yt-dlp", "Download videos from YouTube and other sites", "video media"),
    ("mkvtoolnix", "Create and edit Matroska (MKV) files", "video"),
    ("gifski", "High-quality GIF encoder", "video"),
    ("gifsicle", "Create and optimize GIFs", "video"),
    ("x265", "H.265/HEVC encoder", "video"),
    ("mpv", "Minimal, powerful media player", "video"),
], profiles=(DESIGN,))

# DJ
C_DJ = "DJ & Music Production"
cask(C_DJ, [
    ("mixxx", "Free, open-source DJ software", "dj music"),
    ("rekordbox", "Pioneer DJ library and performance software", "dj music"),
    ("reaper", "Lightweight, powerful DAW", "dj music production"),
    ("bitwig-studio", "DAW for live performance and production", "dj music production"),
    ("ableton-live-lite", "Ableton Live Lite", "dj music production"),
    ("vcv-rack", "Virtual modular synthesizer", "music production"),
    ("sonic-pi", "Live-code music", "music production"),
    ("ocenaudio", "Easy audio editor", "dj audio"),
    ("audacity", "Audio editor", "dj audio"),
    ("audio-hijack", "Record audio from any app", "dj audio"),
    ("soundsource", "Per-app audio control and EQ", "dj audio"),
    ("blackhole-2ch", "Virtual audio driver for routing sound", "dj audio"),
    ("loopback", "Route audio between apps", "dj audio"),
    ("tidal", "Hi-fi music streaming", "dj music"),
    ("obs", "Record or stream your sets", "dj streaming"),
], profiles=(DJ,))
formula(C_DJ, [
    ("sox", "Swiss-army knife of audio manipulation", "dj audio"),
    ("lame", "MP3 encoder", "dj audio"),
    ("flac", "Lossless audio codec", "dj audio"),
    ("ffmpeg", "Convert and process audio and video", "dj audio media"),
    ("yt-dlp", "Download audio and video from many sites", "dj media"),
    ("beets", "Music library manager and tagger", "dj music"),
    ("id3v2", "Edit ID3 tags", "dj music"),
    ("cmus", "Console music player", "dj music"),
    ("mpd", "Music Player Daemon", "dj music"),
], profiles=(DJ,))

# Data Scientist
C_DS = "Data Science & ML"
formula(C_DS, [
    ("python@3.12", "Python 3.12", "python"),
    ("uv", "Extremely fast Python package and project manager", "python rust"),
    ("jupyterlab", "JupyterLab notebooks", "python notebook data"),
    ("numpy", "Fundamental package for array computing", "python data"),
    ("scipy", "Scientific computing library", "python data"),
    ("micromamba", "Tiny conda-compatible package manager", "python data"),
    ("r", "R language for statistical computing", "r data"),
    ("julia", "High-performance language for numerical computing", "julia data"),
    ("octave", "GNU Octave: numerical computation", "data"),
    ("duckdb", "Embedded analytical database", "database sql data"),
    ("graphviz", "Generate diagrams from text", "docs data"),
    ("gnuplot", "Command-driven plotting", "data"),
    ("ollama", "Run LLMs locally", "ai llm"),
    ("llama.cpp", "LLM inference in C/C++", "ai llm"),
    ("visidata", "Terminal spreadsheet for exploring data", "data cli"),
    ("csvkit", "Tools for working with CSV", "data cli"),
    ("qsv", "Very fast CSV toolkit", "data cli rust"),
    ("xan", "CSV magician", "data cli rust"),
    ("pandoc", "Universal document converter", "docs"),
], profiles=(DS,))
cask(C_DS, [
    ("rstudio", "IDE for R", "r data"),
    ("positron", "Next-generation IDE for data science", "data python r"),
    ("miniconda", "Minimal conda installer", "python data"),
    ("anaconda", "Anaconda data science distribution", "python data"),
    ("quarto", "Scientific and technical publishing", "data docs"),
    ("lm-studio", "Discover and run local LLMs", "ai llm"),
    ("visual-studio-code", "Extensible code editor from Microsoft", "editor"),
], profiles=(DS,))

# Data Engineer
C_DE = "Data Pipelines & Streaming"
formula(C_DE, [
    ("apache-spark", "Unified engine for large-scale data processing", "data spark"),
    ("hadoop", "Distributed storage and processing", "data hadoop"),
    ("kafka", "Distributed event streaming platform", "data kafka"),
    ("kcat", "Kafka producer and consumer CLI", "data kafka"),
    ("apache-flink", "Stream processing framework", "data streaming"),
    ("trino", "Distributed SQL query engine", "data sql"),
    ("minio", "S3-compatible object storage", "data storage"),
    ("minio-mc", "MinIO client for S3-compatible storage", "data storage"),
    ("rclone", "Sync files with cloud storage", "data storage"),
    ("snowflake-cli", "Snowflake CLI", "data cloud sql"),
    ("sqlfluff", "SQL linter and formatter", "data sql lint"),
    ("liquibase", "Database schema change management", "data database"),
    ("flyway", "Database migrations", "data database"),
    ("pgloader", "Load data into PostgreSQL", "data database"),
    ("miller", "Like awk/sed/cut for CSV, TSV and JSON", "data cli"),
    ("duckdb", "Embedded analytical database", "database sql data"),
    ("postgresql@16", "PostgreSQL 16 relational database", "database sql"),
    ("mysql", "MySQL relational database", "database sql"),
    ("redis", "In-memory key-value store", "database cache"),
    ("sqlite", "Embedded SQL database", "database sql"),
    ("pgcli", "PostgreSQL client with autocomplete", "database sql python"),
    ("mycli", "MySQL client with autocomplete", "database sql python"),
    ("mongosh", "Official MongoDB shell", "database nosql"),
    ("awscli", "Official AWS CLI", "cloud aws"),
    ("jq", "Command-line JSON processor", "json cli"),
    ("yq", "YAML/JSON/XML processor", "json cli yaml"),
], profiles=(DE,))
cask(C_DE, [
    ("clickhouse", "Fast open-source columnar database", "database data"),
    ("dbeaver-community", "Universal database client", "database sql"),
    ("datagrip", "JetBrains database IDE", "database sql"),
    ("redis-insight", "GUI for Redis", "database"),
    ("tableplus", "Modern, native database client", "database sql"),
], profiles=(DE,))

# Support & Network
C_NETD = "Network Diagnostics"
formula(C_NETD, [
    ("nmap", "Network and port scanner", "network security"),
    ("mtr", "Traceroute and ping combined", "network sre"),
    ("iperf3", "Network throughput testing", "network sre"),
    ("fping", "Ping many hosts at once", "network"),
    ("tcpdump", "Packet capture on the command line", "network"),
    ("wireshark", "Wireshark/tshark command-line tools", "network security"),
    ("socat", "Multipurpose relay (netcat on steroids)", "network"),
    ("netcat", "Read and write data across networks", "network"),
    ("telnet", "Telnet client", "network"),
    ("inetutils", "GNU network utilities (ftp, telnet, ping…)", "network"),
    ("whois", "Look up domain registration data", "network dns"),
    ("doggo", "Friendly DNS client", "network dns"),
    ("ipcalc", "IP subnet calculator", "network"),
    ("speedtest-cli", "Internet speed test from the CLI", "network"),
    ("bandwhich", "Per-process network bandwidth monitor", "network rust"),
    ("iftop", "Live bandwidth usage per connection", "network"),
    ("nload", "Realtime network traffic monitor", "network"),
    ("ngrep", "grep for network traffic", "network"),
    ("lnav", "Log file navigator", "support logs"),
], profiles=(NET,))
cask(C_NETD, [
    ("wireshark-app", "Network packet analyzer", "network security"),
], profiles=(NET,))
C_REMOTE = "Remote Access & VPN"
formula(C_REMOTE, [
    ("mosh", "Mobile shell that survives roaming and sleep", "network ssh"),
    ("autossh", "Keep SSH tunnels alive", "network ssh"),
    ("sshpass", "Non-interactive SSH password auth", "network ssh"),
    ("wireguard-tools", "WireGuard VPN tools", "network vpn"),
    ("tailscale", "Zero-config VPN (CLI)", "network vpn"),
    ("putty", "SSH and serial client", "network ssh"),
    ("tmux", "Terminal multiplexer: sessions, windows and panes", "terminal tmux"),
    ("rsync", "Fast, versatile file copying", "unix"),
], profiles=(NET,))
cask(C_REMOTE, [
    ("termius", "SSH client with sync", "network ssh"),
    ("royal-tsx", "Remote connections manager (RDP, SSH, VNC)", "network remote"),
    ("windows-app", "Microsoft Windows App (remote desktop)", "network remote"),
    ("anydesk", "Remote desktop support", "support remote"),
    ("teamviewer", "Remote support and access", "support remote"),
    ("rustdesk", "Open-source remote desktop", "support remote"),
    ("tailscale-app", "Tailscale for macOS", "network vpn"),
    ("zerotier-one", "Virtual network that just works", "network vpn"),
    ("openvpn-connect", "OpenVPN client", "network vpn"),
    ("cyberduck", "FTP/SFTP/S3 browser", "network"),
    ("zoom", "Video meetings and support calls", "support"),
    ("slack", "Team messaging", "support chat"),
], profiles=(NET,))

# Security
C_PEN = "Pentest & Recon"
formula(C_PEN, [
    ("nmap", "Network and port scanner", "network security"),
    ("masscan", "Very fast TCP port scanner", "security network"),
    ("amass", "Attack surface mapping and asset discovery", "security recon"),
    ("subfinder", "Passive subdomain discovery", "security recon"),
    ("httpx", "Fast HTTP probing toolkit", "security recon"),
    ("naabu", "Fast port scanner", "security recon"),
    ("dnsx", "Fast DNS toolkit", "security recon"),
    ("nuclei", "Template-based vulnerability scanner", "security scanner"),
    ("nikto", "Web server scanner", "security scanner"),
    ("sqlmap", "Automatic SQL injection tool", "security scanner"),
    ("gobuster", "Directory/DNS brute-forcing", "security recon"),
    ("ffuf", "Fast web fuzzer", "security recon"),
    ("feroxbuster", "Fast content discovery", "security recon rust"),
    ("hydra", "Network login cracker", "security cracking"),
    ("hashcat", "Advanced password recovery", "security cracking"),
    ("john-jumbo", "John the Ripper (community edition)", "security cracking"),
    ("testssl", "Test TLS/SSL configuration", "security tls"),
    ("sslscan", "Scan SSL/TLS servers", "security tls"),
], profiles=(SEC,))
cask(C_PEN, [
    ("mitmproxy", "Inspect and modify HTTP(S) traffic", "api http security"),
    ("burp-suite", "Web application security testing", "security web"),
    ("wireshark-app", "Network packet analyzer", "network security"),
], profiles=(SEC,))
C_APPSEC = "AppSec & Hardening"
formula(C_APPSEC, [
    ("trivy", "Vulnerability scanner for images, IaC and repos", "security containers"),
    ("grype", "Container and filesystem vulnerability scanner", "security containers"),
    ("syft", "Generate SBOMs from images and filesystems", "security containers"),
    ("cosign", "Sign and verify container images", "security containers"),
    ("semgrep", "Static analysis with custom rules", "security lint"),
    ("bandit", "Find common security issues in Python code", "security python"),
    ("gitleaks", "Detect secrets in git repos", "security git"),
    ("trufflehog", "Find leaked credentials", "security git"),
    ("checkov", "Static analysis for IaC security and compliance", "iac security lint"),
    ("lynis", "Security auditing for Unix systems", "security audit"),
    ("clamav", "Open-source antivirus engine", "security malware"),
    ("yara", "Pattern matching for malware research", "security malware"),
], profiles=(SEC,))
C_REV = "Reverse Engineering & Forensics"
formula(C_REV, [
    ("radare2", "Reverse engineering framework", "security reverse"),
    ("ghidra", "NSA software reverse engineering suite", "security reverse"),
    ("binwalk", "Firmware analysis tool", "security reverse"),
    ("exiftool", "Read and write file metadata", "media forensics"),
    ("zeek", "Network security monitor", "security network"),
    ("suricata", "Network IDS/IPS and security monitoring", "security network"),
], profiles=(SEC,))
cask(C_REV, [("cutter", "GUI for radare2/Rizin reverse engineering", "security reverse")], profiles=(SEC,))
C_PRIV = "Privacy & Secrets"
formula(C_PRIV, [
    ("gnupg", "GPG: encryption and signatures", "security"),
    ("age", "Simple, modern file encryption", "security"),
    ("sops", "Encrypted secrets files (YAML/JSON/ENV)", "security iac"),
    ("pass", "The standard Unix password manager", "security"),
    ("gopass", "Team password manager for the terminal", "security"),
    ("bitwarden-cli", "Bitwarden CLI", "security"),
    ("openssl@3", "TLS/SSL and crypto library", "security"),
    ("tor", "Anonymizing overlay network", "security privacy"),
], profiles=(SEC,))
cask(C_PRIV, [
    ("keepassxc", "Offline password manager", "security"),
    ("veracrypt", "Disk encryption", "security"),
    ("cryptomator", "Client-side cloud encryption", "security"),
    ("protonvpn", "Proton VPN", "security privacy"),
    ("lulu", "Open-source macOS firewall", "security mac"),
    ("knockknock", "Show persistently installed software", "security mac"),
    ("blockblock", "Alert on persistence attempts", "security mac"),
    ("oversight", "Monitor mic and webcam usage", "security mac"),
    ("malwarebytes", "Malware scanner", "security malware"),
], profiles=(SEC,))

# ───────────────────── Kits for the new profiles ─────────────────────
KITS.extend([
    Kit("QA Web Automation", "Selenium, browsers, Lighthouse and API checks", QA,
        ("formula:selenium-server", "formula:geckodriver", "cask:google-chrome",
         "cask:firefox", "formula:lighthouse", "formula:newman", "formula:hurl", "cask:bruno")),
    Kit("QA Mobile", "Appium, Maestro and Android tooling", QA,
        ("formula:appium", "cask:maestro", "cask:android-studio", "formula:pytest")),
    Kit("QA Load Testing", "k6, JMeter, Locust and reports", QA,
        ("formula:k6", "formula:jmeter", "formula:locust", "formula:allure", "formula:httpie")),
    Kit("Office Essentials", "Docs, notes, chat and window management", OFFICE,
        ("cask:libreoffice", "cask:obsidian", "cask:notion", "cask:slack", "cask:zoom",
         "cask:rectangle", "cask:raycast", "cask:keka", "cask:bitwarden")),
    Kit("PDF & Documents", "Edit, OCR and convert documents", OFFICE,
        ("formula:pandoc", "formula:ghostscript", "formula:qpdf", "formula:tesseract",
         "formula:ocrmypdf", "cask:skim", "cask:pdfsam-basic")),
    Kit("Web Designer", "UI design, optimization and previews", DESIGN,
        ("cask:figma", "cask:responsively", "cask:imageoptim", "cask:colorsnapper", "formula:svgo",
         "formula:webp", "cask:font-inter")),
    Kit("Graphic Designer", "Vector, raster, photo and 3D", DESIGN,
        ("cask:inkscape", "cask:gimp", "cask:krita", "cask:blender",
         "formula:imagemagick")),
    Kit("Video Creator", "Edit, convert and publish video", DESIGN,
        ("cask:kdenlive", "cask:shotcut", "cask:handbrake-app", "cask:obs", "cask:iina",
         "formula:ffmpeg", "formula:yt-dlp", "cask:audacity")),
    Kit("DJ Starter", "Mix, record and route audio", DJ,
        ("cask:mixxx", "cask:audacity", "cask:blackhole-2ch", "cask:audio-hijack", "formula:ffmpeg",
         "formula:sox", "formula:lame", "formula:flac")),
    Kit("Music Producer", "DAWs and synths for production", DJ,
        ("cask:reaper", "cask:bitwig-studio", "cask:vcv-rack", "cask:sonic-pi",
         "cask:ocenaudio")),
    Kit("Data Science Lab", "Python, notebooks and analysis tools", DS,
        ("formula:python@3.12", "formula:uv", "formula:jupyterlab", "formula:numpy", "formula:scipy",
         "formula:duckdb", "formula:visidata", "formula:csvkit", "formula:graphviz")),
    Kit("R & Statistics", "R, RStudio and Quarto", DS,
        ("formula:r", "cask:rstudio", "cask:quarto", "formula:pandoc", "formula:gnuplot")),
    Kit("Local AI", "Run LLMs on your machine", DS,
        ("formula:ollama", "formula:llama.cpp", "cask:lm-studio", "formula:uv")),
    Kit("Data Engineering Core", "Spark, Kafka and warehouse tooling", DE,
        ("formula:apache-spark", "formula:kafka", "formula:kcat", "formula:trino", "formula:duckdb",
         "formula:sqlfluff", "formula:rclone", "formula:minio-mc", "formula:awscli")),
    Kit("Databases & Migrations", "Engines, clients and migration tools", DE,
        ("formula:postgresql@16", "formula:mysql", "formula:redis", "formula:pgcli", "formula:mycli",
         "formula:flyway", "formula:liquibase", "cask:dbeaver-community")),
    Kit("Network Troubleshooting", "Diagnose connectivity and performance", NET,
        ("formula:nmap", "formula:mtr", "formula:iperf3", "formula:fping", "formula:tcpdump",
         "formula:doggo", "formula:whois", "formula:speedtest-cli", "formula:bandwhich")),
    Kit("Remote Support", "Remote desktop, SSH and VPN for helpdesk work", NET,
        ("cask:rustdesk", "cask:anydesk", "cask:termius", "formula:mosh", "formula:tailscale",
         "cask:windows-app")),
    Kit("Pentest Starter", "Recon, scanning and web testing", SEC,
        ("formula:nmap", "formula:amass", "formula:subfinder", "formula:httpx", "formula:nuclei",
         "formula:ffuf", "formula:gobuster", "cask:burp-suite")),
    Kit("AppSec & Secrets", "Find vulnerabilities and leaked secrets in code", SEC,
        ("formula:semgrep", "formula:bandit", "formula:gitleaks", "formula:trufflehog", "formula:trivy",
         "formula:checkov", "formula:sops")),
    Kit("Privacy & Hardening", "Encryption, password managers and Mac firewall", SEC,
        ("cask:keepassxc", "cask:veracrypt", "cask:cryptomator", "cask:lulu", "cask:oversight",
         "formula:gnupg", "formula:age")),
])

# ───────────────────── Vendor stacks ─────────────────────
V = (VENDOR,)
C_MS = "Microsoft"
cask(C_MS, [
    ("visual-studio-code", "Extensible code editor from Microsoft", "editor microsoft"),
    ("azure-cli", "Official Azure CLI", "cloud azure microsoft"),
    ("microsoft-azure-storage-explorer", "Manage Azure storage accounts", "cloud azure microsoft"),
    ("dotnet-sdk", ".NET SDK installer package", "dotnet csharp microsoft"),
    ("github", "GitHub Desktop", "git github microsoft"),
    ("microsoft-edge", "Microsoft Edge browser", "browser microsoft"),
    ("microsoft-teams", "Microsoft Teams", "office chat microsoft"),
    ("microsoft-office", "Microsoft 365 apps (Word, Excel, PowerPoint)", "office microsoft"),
    ("microsoft-outlook", "Outlook email and calendar", "office mail microsoft"),
    ("microsoft-excel", "Excel", "office microsoft"),
    ("microsoft-word", "Word", "office microsoft"),
    ("microsoft-powerpoint", "PowerPoint", "office microsoft"),
    ("microsoft-onenote", "OneNote", "office notes microsoft"),
    ("onedrive", "OneDrive sync", "office cloud microsoft"),
    ("windows-app", "Windows App (remote desktop to Windows PCs and Azure Virtual Desktop)",
     "remote microsoft"),
    ("microsoft-auto-update", "Microsoft AutoUpdate for Office", "office microsoft"),
], profiles=V)
formula(C_MS, [
    ("dotnet", "Microsoft .NET SDK (latest)", "dotnet csharp microsoft"),
    ("powershell", "PowerShell shell and scripting language", "dotnet shell microsoft"),
    ("sqlcmd", "Go-based sqlcmd for SQL Server", "database sql microsoft"),
    ("azurite", "Azure Storage emulator for local development", "cloud azure microsoft"),
    ("typescript", "TypeScript compiler", "node web typescript microsoft"),
    ("gh", "GitHub CLI", "git github microsoft"),
], profiles=V)

C_ORA = "Oracle"
cask(C_ORA, [
    ("oracle-jdk", "Oracle JDK (latest)", "java oracle"),
    ("oracle-jdk@21", "Oracle JDK 21 (LTS)", "java oracle"),
    ("graalvm-jdk", "Oracle GraalVM JDK: JIT and native-image", "java oracle graalvm"),
    ("sqlcl", "Oracle SQLcl: modern SQL*Plus replacement", "database sql oracle"),
    ("mysql-shell", "MySQL Shell: SQL, JavaScript and Python", "database sql mysql oracle"),
    ("virtualbox", "Oracle VM VirtualBox", "virtualization oracle"),
    ("jdk-mission-control", "Java Flight Recorder analysis and profiling", "java monitor oracle"),
], profiles=V)
formula(C_ORA, [
    ("mysql", "MySQL relational database", "database sql mysql oracle"),
    ("mysql-client", "MySQL command-line client", "database sql mysql oracle"),
    ("oci-cli", "Oracle Cloud Infrastructure CLI", "cloud oracle"),
    ("openjdk", "OpenJDK, the open-source base of Oracle JDK", "java oracle"),
    ("helidon", "Helidon CLI for Java microservices", "java oracle"),
], profiles=V)

C_APPLE = "Apple Developer"
formula(C_APPLE, [
    ("swift", "Swift toolchain", "swift apple"),
    ("swiftly", "Swift toolchain installer and version manager", "swift apple"),
    ("swiftformat", "Swift code formatter", "swift apple lint"),
    ("swiftlint", "Swift style and conventions linter", "swift apple lint"),
    ("swiftgen", "Generate Swift code for resources", "swift apple"),
    ("sourcery", "Meta-programming for Swift", "swift apple"),
    ("mint", "Install and run Swift command-line tools", "swift apple"),
    ("xcodegen", "Generate Xcode projects from a spec", "xcode apple"),
    ("xcodes", "Install and switch between Xcode versions", "xcode apple"),
    ("xcbeautify", "Prettier xcodebuild output", "xcode apple"),
    ("xcresultparser", "Parse .xcresult bundles", "xcode apple"),
    ("xcode-build-server", "Build server for Xcode projects (sourcekit-lsp)", "xcode apple"),
    ("periphery", "Find unused Swift code", "swift apple lint"),
    ("swift-outdated", "Check outdated Swift package dependencies", "swift apple"),
    ("fastlane", "Automate building and releasing iOS and Android apps", "mobile apple ci"),
    ("cocoapods", "Dependency manager for Swift and Objective-C", "mobile apple"),
    ("carthage", "Decentralized dependency manager for Cocoa", "mobile apple"),
    ("mas", "Mac App Store command-line interface", "apple"),
    ("create-dmg", "Create a nice DMG for your app", "apple"),
    ("ios-deploy", "Install and debug iOS apps from the command line", "mobile apple"),
    ("libimobiledevice", "Talk to iOS devices", "mobile apple"),
    ("ideviceinstaller", "Manage apps on iOS devices", "mobile apple"),
    ("container", "Apple's tool to run Linux containers as lightweight VMs", "containers apple"),
    ("lima", "Linux virtual machines on macOS", "containers apple"),
], profiles=V, platforms=(MAC,))
cask(C_APPLE, [
    ("xcodes-app", "Xcodes: install and manage Xcode versions (GUI)", "xcode apple"),
    ("sf-symbols", "Apple's SF Symbols icon library", "design apple"),
    ("tuist", "Tuist: generate and manage Xcode projects", "xcode apple"),
    ("proxyman", "HTTP debugging proxy for macOS and iOS", "api http apple"),
    ("swiftformat-for-xcode", "SwiftFormat Xcode source editor extension", "swift apple"),
], profiles=V)

C_OSS = "Open Source Apps"
cask(C_OSS, [
    ("libreoffice", "Full open-source office suite", "office opensource"),
    ("firefox", "Firefox browser", "browser opensource"),
    ("thunderbird", "Email client", "mail opensource"),
    ("vscodium", "VS Code without Microsoft telemetry", "editor opensource"),
    ("gimp", "Raster image editor", "design opensource"),
    ("inkscape", "Vector graphics editor", "design opensource"),
    ("krita", "Digital painting and illustration", "design opensource"),
    ("blender", "3D modeling, animation and rendering", "design 3d opensource"),
    ("kdenlive", "Open-source video editor", "video opensource"),
    ("obs", "Recording and live streaming", "video streaming opensource"),
    ("vlc", "Media player that plays everything", "media opensource"),
    ("audacity", "Audio editor", "audio opensource"),
    ("handbrake-app", "Video transcoder", "video opensource"),
    ("keepassxc", "Offline password manager", "security opensource"),
    ("bitwarden", "Open-source password manager", "security opensource"),
    ("signal", "Private messenger", "chat security opensource"),
    ("element", "Matrix chat client", "chat opensource"),
    ("nextcloud", "Self-hosted cloud sync client", "cloud opensource"),
    ("jellyfin", "Free media server", "media opensource"),
    ("calibre", "E-book manager and converter", "office opensource"),
    ("zotero", "Reference manager for research", "office research opensource"),
    ("joplin", "Markdown notes with sync", "office notes opensource"),
    ("godot", "Open-source 2D/3D game engine", "gamedev opensource"),
    ("tor-browser", "Tor Browser for privacy", "browser security opensource"),
    ("ghostty", "Fast, native, GPU-accelerated terminal", "terminal opensource"),
], profiles=V)
formula(C_OSS, [
    ("neovim", "Modernized Vim, extensible with Lua", "editor vim opensource"),
    ("gitea", "Lightweight self-hosted Git service", "git opensource"),
    ("syncthing", "Continuous file synchronization between devices", "network opensource"),
], profiles=V)

C_RH = "Red Hat"
formula(C_RH, [
    ("podman", "Daemonless container engine (OCI)", "containers redhat"),
    ("podman-compose", "docker-compose for Podman", "containers redhat"),
    ("skopeo", "Work with remote container images and registries", "containers redhat"),
    ("openshift-cli", "OpenShift CLI (oc)", "k8s redhat openshift"),
    ("odo", "Developer-focused CLI for OpenShift and Kubernetes", "k8s redhat openshift"),
    ("operator-sdk", "Build Kubernetes Operators", "k8s redhat"),
    ("rosa-cli", "Red Hat OpenShift Service on AWS CLI", "cloud aws redhat openshift"),
    ("tektoncd-cli", "Tekton CI/CD pipelines CLI", "k8s ci redhat"),
    ("ansible", "Automation and configuration management", "iac devops redhat"),
    ("ansible-lint", "Best-practices linter for Ansible", "iac devops lint redhat"),
    ("butane", "Convert Butane configs to Ignition (Fedora CoreOS)", "iac redhat"),
    ("virt-manager", "Desktop UI for managing virtual machines (libvirt)", "virtualization redhat"),
    ("kubernetes-cli", "Kubernetes CLI (kubectl)", "k8s containers"),
    ("helm", "Kubernetes package manager", "k8s containers"),
    ("kustomize", "Customize Kubernetes manifests without templates", "k8s containers"),
    ("argocd", "Argo CD CLI for GitOps", "k8s gitops"),
    ("minikube", "Local Kubernetes for development", "k8s containers"),
    ("maven", "Java build and dependency management", "java redhat"),
    ("tomcat", "Apache Tomcat servlet container", "java web redhat"),
], profiles=V)
cask(C_RH, [
    ("podman-desktop", "GUI for Podman and Kubernetes", "containers redhat"),
], profiles=V)

C_JB = "JetBrains"
cask(C_JB, [
    ("jetbrains-toolbox", "Manager for all JetBrains IDEs", "ide jetbrains"),
    ("intellij-idea", "IntelliJ IDEA Ultimate (Java, Kotlin, Spring…)", "ide java kotlin jetbrains"),
    ("intellij-idea-ce", "IntelliJ IDEA Community Edition", "ide java kotlin jetbrains"),
    ("pycharm", "PyCharm Professional", "ide python jetbrains"),
    ("pycharm-ce", "PyCharm Community Edition", "ide python jetbrains"),
    ("webstorm", "WebStorm: JavaScript and TypeScript IDE", "ide web jetbrains"),
    ("phpstorm", "PhpStorm: PHP IDE", "ide php jetbrains"),
    ("goland", "GoLand: Go IDE", "ide go jetbrains"),
    ("rubymine", "RubyMine: Ruby and Rails IDE", "ide ruby jetbrains"),
    ("clion", "CLion: C and C++ IDE", "ide cpp jetbrains"),
    ("rider", "Rider: .NET and game dev IDE", "ide dotnet jetbrains"),
    ("rustrover", "RustRover: Rust IDE", "ide rust jetbrains"),
    ("datagrip", "DataGrip: databases and SQL IDE", "ide database jetbrains"),
    ("android-studio", "Android Studio (built on IntelliJ)", "ide mobile jetbrains"),
    ("font-jetbrains-mono", "JetBrains Mono typeface for code", "font jetbrains"),
    ("font-jetbrains-mono-nerd-font", "JetBrains Mono with Nerd Font icons", "font terminal jetbrains"),
], profiles=V)
formula(C_JB, [
    ("kotlin", "Kotlin programming language", "kotlin java jetbrains"),
    ("ktlint", "Kotlin linter and formatter", "kotlin lint jetbrains"),
    ("detekt", "Static code analysis for Kotlin", "kotlin lint jetbrains"),
    ("jbang", "Run Java as scripts", "java jetbrains"),
], profiles=V)

KITS.extend([
    Kit("Microsoft Developer", "VS Code, .NET, PowerShell, Azure and GitHub", VENDOR,
        ("cask:visual-studio-code", "formula:dotnet", "formula:powershell", "cask:azure-cli", "formula:gh", "formula:typescript")),
    Kit("Microsoft 365", "Office apps, Teams, OneDrive and remote desktop", VENDOR,
        ("cask:microsoft-office", "cask:microsoft-teams", "cask:onedrive", "cask:microsoft-edge",
         "cask:windows-app")),
    Kit("Oracle Java & Databases", "Oracle JDK, GraalVM, MySQL and SQLcl", VENDOR,
        ("cask:oracle-jdk", "cask:graalvm-jdk", "formula:mysql", "cask:mysql-shell", "cask:sqlcl",
         "formula:oci-cli", "cask:virtualbox")),
    Kit("iOS & macOS Developer", "Swift tooling, Xcode helpers and release automation", VENDOR,
        ("formula:xcodes", "formula:swiftlint", "formula:swiftformat", "formula:xcodegen",
         "formula:xcbeautify", "formula:fastlane", "formula:cocoapods", "cask:sf-symbols",
         "cask:proxyman")),
    Kit("Open Source Desktop", "A full desktop of open-source apps", VENDOR,
        ("cask:libreoffice", "cask:firefox", "cask:thunderbird", "cask:vlc", "cask:gimp",
         "cask:inkscape", "cask:keepassxc", "cask:obs")),
    Kit("Red Hat Containers & OpenShift", "Podman, OpenShift CLI, Ansible and GitOps", VENDOR,
        ("formula:podman", "cask:podman-desktop", "formula:skopeo", "formula:openshift-cli",
         "formula:operator-sdk", "formula:ansible", "formula:ansible-lint", "formula:kubernetes-cli",
         "formula:helm")),
    Kit("JetBrains IDEs", "Toolbox plus the most popular IDEs", VENDOR,
        ("cask:jetbrains-toolbox", "cask:intellij-idea-ce", "cask:pycharm-ce", "cask:webstorm",
         "cask:goland", "cask:datagrip", "cask:font-jetbrains-mono")),
])

# Merge duplicate keys (same package listed in several areas): keep the first, union profiles/tags.
_merged: dict = {}
for _it in ITEMS:
    if _it.key in _merged:
        _o = _merged[_it.key]
        _merged[_it.key] = Item(_o.name, _o.kind, _o.category, _o.desc,
                                tuple(dict.fromkeys(_o.profiles + _it.profiles)), _o.platforms,
                                tuple(dict.fromkeys(_o.tags + _it.tags)), _o.tap or _it.tap,
                                tuple(dict.fromkeys(_o.groups + _it.groups
                                                    + ((_it.category,) if _it.category != _o.category else ()))))
    else:
        _merged[_it.key] = _it
ITEMS[:] = list(_merged.values())

# Existing Dev tooling is also useful for SRE/Cloud profiles.
for _i, _it in enumerate(ITEMS):
    if _it.category in (C_CONT, C_API) and SRE not in _it.profiles:
        ITEMS[_i] = _dc_replace(_it, profiles=_it.profiles + (SRE,))

CATEGORIES_DEV = [C_TERM, C_EDIT, C_GIT, C_LANG, C_NODE, C_GO, C_NET, C_JAVA, C_SHELL, C_MAIN,
                  C_CONT, C_DB, C_API, C_UTIL, C_FONT]
CATEGORIES_SRE = [C_CLOUD, C_IAC, C_K8S, C_CONT, C_PAAS, C_OBS, C_API]
CATEGORIES_GAMER = [C_STORE, C_COMP, C_EMU, C_STREAM, C_ENG, C_PERF]
PROFILE_CATEGORIES = {
    DEV: CATEGORIES_DEV,
    SRE: CATEGORIES_SRE,
    QA: [C_QA_AUTO, C_QA_PERF],
    DS: [C_DS],
    DE: [C_DE],
    NET: [C_NETD, C_REMOTE],
    SEC: [C_PEN, C_APPSEC, C_REV, C_PRIV],
    VENDOR: [C_MS, C_ORA, C_APPLE, C_OSS, C_RH, C_JB],
    DESIGN: [C_DWEB, C_DGFX, C_DVID],
    DJ: [C_DJ],
    OFFICE: [C_OFFICE, "Communication & Cloud Drive", "Documents & PDF Tools"],
    GAMER: CATEGORIES_GAMER,
}
ALL_CATEGORIES = list(dict.fromkeys(c for cats in PROFILE_CATEGORIES.values() for c in cats))

BY_KEY = {i.key: i for i in ITEMS}

# Baseline picks suggested when nothing relevant is installed yet.
ESSENTIALS = {
    DEV: ["formula:git", "formula:ripgrep", "formula:fzf", "formula:jq", "cask:visual-studio-code",
          "formula:starship", "formula:gh", "formula:btop"],
    SRE: ["formula:kubernetes-cli", "formula:k9s", "formula:terraform", "formula:awscli",
          "cask:gcloud-cli", "cask:azure-cli", "formula:helm", "formula:jq", "formula:trivy"],
    QA: ["cask:google-chrome", "cask:postman", "formula:k6", "formula:hurl"],
    DS: ["formula:python@3.12", "formula:uv", "formula:jupyterlab", "formula:duckdb", "formula:visidata"],
    DE: ["formula:apache-spark", "formula:kafka", "formula:duckdb", "formula:postgresql@16", "formula:awscli"],
    NET: ["formula:nmap", "formula:mtr", "cask:wireshark-app", "formula:iperf3", "cask:termius"],
    SEC: ["formula:nmap", "cask:burp-suite", "formula:trivy", "formula:gitleaks", "cask:keepassxc"],
    DESIGN: ["cask:figma", "cask:inkscape", "cask:gimp", "cask:kdenlive", "formula:ffmpeg"],
    DJ: ["cask:mixxx", "cask:audacity", "cask:blackhole-2ch", "cask:reaper", "formula:ffmpeg"],
    OFFICE: ["cask:libreoffice", "cask:obsidian", "cask:slack", "cask:zoom", "cask:rectangle"],
    VENDOR: ["cask:visual-studio-code", "cask:jetbrains-toolbox", "formula:podman", "formula:swiftlint",
             "cask:oracle-jdk", "cask:libreoffice", "cask:firefox", "formula:dotnet"],
    GAMER: ["cask:steam", "cask:discord", "cask:obs", "cask:heroic", "cask:retroarch",
            "formula:btop", "cask:stats", "cask:vlc"],
}


# ───────────────────── Lookup helpers (used by the GUI-less CLI and the tests) ─────────────────────
PROFILE_SLUGS = {
    "dev": DEV, "sre": SRE, "qa": QA, "datascience": DS, "dataeng": DE, "network": NET,
    "security": SEC, "design": DESIGN, "dj": DJ, "office": OFFICE, "vendors": VENDOR, "gamer": GAMER,
}


def find_items(query: str = "", profile=None, platform=None, category=None) -> List[Item]:
    """Curated items matching every word of `query` (name, description, category, tags)."""
    words = query.lower().split()
    out = []
    for i in ITEMS:
        if profile and profile not in i.profiles:
            continue
        if platform and platform not in i.platforms:
            continue
        if category and category != i.category and category not in i.groups:
            continue
        hay = " ".join((i.name, i.desc, i.category, *i.tags)).lower()
        if all(w in hay for w in words):
            out.append(i)
    return sorted(out, key=lambda i: (i.name, i.kind))


def _slug(text: str) -> str:
    return "-".join("".join(c if c.isalnum() else " " for c in text.lower()).split())


def find_kit(name: str) -> Optional[Kit]:
    """Kit by exact name or slug, or by a unique slug prefix. None when missing or ambiguous."""
    want = _slug(name)
    for k in KITS:
        if k.name.lower() == name.lower() or _slug(k.name) == want:
            return k
    hits = [k for k in KITS if _slug(k.name).startswith(want)] if want else []
    return hits[0] if len(hits) == 1 else None


def resolve_packages(name: str) -> List[Item]:
    """Items called `name` ("kind:name" selects one kind)."""
    if ":" in name:
        item = BY_KEY.get(name)
        return [item] if item else []
    return [i for i in ITEMS if i.name == name]


def brewfile_lines(items) -> List[str]:
    return [f'{"cask" if i.kind == "cask" else "brew"} "{i.full_name}"' for i in items]
