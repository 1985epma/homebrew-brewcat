//! `brewcat doctor`: check this machine and print how to fix what is wrong, and the redacted Markdown report for
//! a GitHub issue. Runs without a window and without Homebrew.

use std::collections::BTreeSet;
use std::path::{Path, PathBuf};

use serde::Serialize;
use serde_json::{Value, json};

use crate::help_text::VERSION;
use crate::{brewenv, launcher, sys};

pub const TAP: &str = "1985epma/brewcat";

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
pub enum Status {
    #[serde(rename = "OK")]
    Ok,
    #[serde(rename = "WARN")]
    Warn,
    #[serde(rename = "FAIL")]
    Fail,
}

impl Status {
    pub fn as_str(self) -> &'static str {
        match self {
            Status::Ok => "OK",
            Status::Warn => "WARN",
            Status::Fail => "FAIL",
        }
    }
}

#[derive(Debug, Clone, Serialize)]
pub struct Check {
    pub name: String,
    pub status: Status,
    pub detail: String,
    pub hint: String,
}

fn check(name: &str, status: Status, detail: impl Into<String>, hint: impl Into<String>) -> Check {
    Check { name: name.to_string(), status, detail: detail.into(), hint: hint.into() }
}

fn run(parts: &[&str]) -> String {
    sys::run_text(parts, 15)
}

/// Entries of Homebrew's tap trust list (`brew trust`).
fn trusted_entries(home: &Path) -> Vec<String> {
    let path = match std::env::var_os("XDG_CONFIG_HOME").filter(|c| !c.is_empty()) {
        Some(cfg) => PathBuf::from(cfg).join("homebrew/trust.json"),
        None => home.join(".homebrew/trust.json"),
    };
    let Ok(Value::Object(data)) = std::fs::read_to_string(path).map_err(|_| ()).and_then(|t| serde_json::from_str(&t).map_err(|_| ()))
    else {
        return Vec::new();
    };
    data.values().filter_map(Value::as_array).flatten().filter_map(Value::as_str).map(String::from).collect()
}

/// True when a graphics library the window can use (OpenGL, EGL or Vulkan) is installed. Linux only.
fn has_graphics_library() -> bool {
    let dirs = [
        "/usr/lib",
        "/usr/lib64",
        "/lib",
        "/lib64",
        "/usr/lib/x86_64-linux-gnu",
        "/usr/lib/aarch64-linux-gnu",
        "/lib/x86_64-linux-gnu",
        "/lib/aarch64-linux-gnu",
        "/usr/local/lib",
        "/home/linuxbrew/.linuxbrew/lib",
    ];
    let libs = ["libEGL.so.1", "libGL.so.1", "libvulkan.so.1"];
    dirs.iter().any(|d| libs.iter().any(|l| Path::new(d).join(l).exists()))
}

pub fn collect_checks() -> Vec<Check> {
    let mut checks = Vec::new();
    let mac = sys::is_mac();
    let silicon = brewenv::apple_silicon();
    let home = sys::home_dir();

    checks.push(check("brewcat", Status::Ok, VERSION, ""));
    checks.push(check("system", Status::Ok, sys::os_description(), ""));

    if mac && silicon && sys::machine() != "arm64" {
        checks.push(check(
            "rosetta translation",
            Status::Warn,
            "this process runs under Rosetta (x86_64) on Apple Silicon",
            "Use the native (arm64) brewcat: reinstall it with Homebrew's arm64 prefix (/opt/homebrew) or launch it from a native terminal",
        ));
    }
    if mac && silicon {
        let has_rosetta = Path::new("/Library/Apple/usr/share/rosetta/rosetta").exists();
        checks.push(check(
            "rosetta 2",
            if has_rosetta { Status::Ok } else { Status::Warn },
            if has_rosetta { "installed" } else { "not installed (only needed for Intel-only apps)" },
            if has_rosetta { "" } else { "softwareupdate --install-rosetta --agree-to-license" },
        ));
    }

    if cfg!(feature = "gui") {
        checks.push(check("window", Status::Ok, "this build has the window", ""));
    } else {
        checks.push(check(
            "window",
            Status::Warn,
            "this build has no window (command line only)",
            "Build with the default features: cargo install brewcat",
        ));
    }
    if !mac {
        let has_display = std::env::var_os("DISPLAY").is_some_and(|v| !v.is_empty())
            || std::env::var_os("WAYLAND_DISPLAY").is_some_and(|v| !v.is_empty());
        checks.push(check(
            "display",
            if has_display { Status::Ok } else { Status::Warn },
            if has_display { "graphical session found" } else { "no DISPLAY/WAYLAND_DISPLAY" },
            if has_display { "" } else { "the window needs a graphical session" },
        ));
        let gfx = has_graphics_library();
        checks.push(check(
            "graphics",
            if gfx { Status::Ok } else { Status::Warn },
            if gfx { "OpenGL/EGL/Vulkan library found" } else { "no OpenGL, EGL or Vulkan library found" },
            if gfx { "" } else { "Install your GPU drivers or Mesa (Debian/Ubuntu: sudo apt install libegl1 libgl1)" },
        ));
    }

    match brewenv::find_brew() {
        None => checks.push(check("homebrew", Status::Fail, "brew not found", "Install Homebrew from https://brew.sh")),
        Some(brew) => {
            let version = run(&[&brew, "--version"]).lines().next().unwrap_or("unknown").to_string();
            checks.push(check("homebrew", Status::Ok, format!("{version} ({brew})"), ""));
            if mac && silicon && brew.starts_with("/usr/local") {
                checks.push(check(
                    "homebrew architecture",
                    Status::Warn,
                    "Intel Homebrew (/usr/local) on an Apple Silicon Mac",
                    "Native Homebrew lives in /opt/homebrew; brewcat runs brew via `arch` when needed",
                ));
            }
            let repo = run(&[&brew, "--repository"]);
            let repo = if repo.is_empty() { "/nonexistent".to_string() } else { repo };
            if Path::new(&repo).join("Library/Taps/1985epma/homebrew-brewcat").exists() {
                let prefix = format!("{TAP}/");
                let trusted = trusted_entries(&home).iter().any(|e| e == TAP || e.starts_with(&prefix));
                checks.push(check(
                    "brewcat tap",
                    if trusted { Status::Ok } else { Status::Warn },
                    format!("{TAP} is {}", if trusted { "trusted" } else { "not trusted" }),
                    if trusted { String::new() } else { format!("brew trust {TAP}") },
                ));
            }
        }
    }

    if sys::which("git").is_some() {
        checks.push(check("git", Status::Ok, run(&["git", "--version"]), ""));
    } else {
        checks.push(check("git", Status::Warn, "git not found (needed to install skills from GitHub)", "Install git (brew install git)"));
    }

    if mac {
        let user_app = home.join("Applications/brewcat.app");
        let sys_app = Path::new("/Applications/brewcat.app");
        if user_app.exists() || sys_app.exists() {
            let where_ = if user_app.exists() { "~/Applications" } else { "/Applications" };
            let problem = if user_app.exists() { launcher::bundle_state(&home) } else { None };
            match problem {
                Some(problem) => checks.push(check(
                    "brewcat.app",
                    Status::Warn,
                    format!("found in {where_} but {problem}"),
                    "Run `brewcat --install-app` to rebuild it",
                )),
                None => checks.push(check("brewcat.app", Status::Ok, format!("found in {where_}"), "")),
            }
        } else {
            checks.push(check(
                "brewcat.app",
                Status::Warn,
                "not in ~/Applications or /Applications",
                "Run `brewcat --install-app` or `brew install --cask 1985epma/brewcat/brewcat`",
            ));
        }
        let askpass = sys::config_dir_in(&home).join("askpass.sh");
        let ready = askpass.exists();
        checks.push(check(
            "sudo password dialog",
            if ready { Status::Ok } else { Status::Warn },
            if ready { "askpass helper ready" } else { "created on first cask install" },
            "",
        ));
    }
    checks
}

/// Print the checks (or JSON) and return the exit code: 1 when a check failed.
pub fn doctor(as_json: bool) -> i32 {
    let checks = collect_checks();
    let failed = checks.iter().any(|c| c.status == Status::Fail);
    if as_json {
        let doc = json!({"version": VERSION, "ok": !failed, "checks": checks});
        println!("{}", serde_json::to_string_pretty(&doc).unwrap_or_default());
    } else {
        let width = checks.iter().map(|c| c.name.chars().count()).max().unwrap_or(0);
        for c in &checks {
            println!("[{:<4}] {:<width$}  {}", c.status.as_str(), c.name, c.detail);
            if !c.hint.is_empty() {
                println!("       {:<width$}  → {}", "", c.hint);
            }
        }
        let warns = checks.iter().filter(|c| c.status == Status::Warn).count();
        let fails = checks.iter().filter(|c| c.status == Status::Fail).count();
        let mut counts = Vec::new();
        if fails > 0 {
            counts.push(format!("{fails} failure(s)"));
        }
        if warns > 0 {
            counts.push(format!("{warns} warning(s)"));
        }
        let counts = if counts.is_empty() { String::new() } else { format!(" ({})", counts.join(", ")) };
        println!("\n{}{counts}.", if failed { "Problems found" } else { "No blocking problems" });
    }
    i32::from(failed)
}

/// What identifies the person or the machine, to be hidden from a report.
#[derive(Debug, Default, Clone)]
pub struct Redactor {
    pub homes: BTreeSet<String>,
    pub users: BTreeSet<String>,
    pub hosts: BTreeSet<String>,
}

fn is_word_char(c: char) -> bool {
    c.is_ascii_alphanumeric()
}

/// Replace `needle` by `token` wherever it is not part of a longer alphanumeric word.
fn replace_word(text: &str, needle: &str, token: &str) -> String {
    let mut out = String::with_capacity(text.len());
    let mut last = 0;
    for (start, _) in text.match_indices(needle) {
        if start < last {
            continue;
        }
        let end = start + needle.len();
        let before_ok = text[..start].chars().next_back().is_none_or(|c| !is_word_char(c));
        let after_ok = text[end..].chars().next().is_none_or(|c| !is_word_char(c));
        if before_ok && after_ok {
            out.push_str(&text[last..start]);
            out.push_str(token);
            last = end;
        }
    }
    out.push_str(&text[last..]);
    out
}

impl Redactor {
    /// The home directory, user names and host name of this machine.
    pub fn from_env() -> Redactor {
        let home = sys::home_dir();
        let mut r = Redactor::default();
        for h in [std::env::var("HOME").unwrap_or_default(), home.to_string_lossy().into_owned()] {
            if h.chars().count() > 1 {
                if let Ok(real) = std::fs::canonicalize(&h) {
                    r.homes.insert(real.to_string_lossy().into_owned());
                }
                r.homes.insert(h);
            }
        }
        for var in ["USER", "LOGNAME", "USERNAME"] {
            r.users.extend(std::env::var(var).ok());
        }
        r.users.extend(home.file_name().map(|n| n.to_string_lossy().into_owned()));
        let login = run(&["id", "-un"]); // the account name, also when $USER is not set
        if !login.is_empty() {
            r.users.insert(login);
        }
        r.hosts.extend(sys::hostname());
        r
    }

    /// The home directory becomes `~`, the user names `<user>` and the host names `<host>`.
    pub fn redact(&self, text: &str) -> String {
        let mut homes: Vec<&String> = self.homes.iter().filter(|h| h.chars().count() > 1).collect();
        homes.sort_by_key(|h| std::cmp::Reverse(h.len()));
        let mut text = text.to_string();
        for h in homes {
            text = text.replace(h.as_str(), "~");
        }
        for (names, token) in [(&self.users, "<user>"), (&self.hosts, "<host>")] {
            let mut names: Vec<&String> = names.iter().filter(|n| n.chars().count() > 1).collect();
            names.sort_by_key(|n| std::cmp::Reverse(n.len()));
            for n in names {
                text = replace_word(&text, n, token);
            }
        }
        text
    }
}

/// Markdown for pasting into a GitHub issue, built from the given checks. Versions and checks only: no
/// environment variables, file contents, host or user name; the home directory is shown as `~`.
pub fn render_report(checks: &[Check], homebrew: &str, redactor: &Redactor) -> String {
    let window = if cfg!(feature = "gui") { "egui" } else { "none (command line only)" };
    let mut lines = vec![
        "### brewcat diagnostics".to_string(),
        String::new(),
        format!("- brewcat: {VERSION}"),
        format!("- OS: {}", sys::os_description()),
        format!("- Architecture: {}", sys::machine()),
        format!("- Window: {window}"),
        format!("- Homebrew: {homebrew}"),
        String::new(),
        "```text".to_string(),
    ];
    for c in checks {
        lines.push(format!("[{}] {}: {}", c.status.as_str(), c.name, c.detail));
        if !c.hint.is_empty() {
            lines.push(format!("       fix: {}", c.hint));
        }
    }
    lines.push("```".to_string());
    format!("{}\n", redactor.redact(&lines.join("\n")))
}

pub fn diagnostic_report() -> String {
    let homebrew = match brewenv::find_brew() {
        Some(brew) => run(&[&brew, "--version"]).lines().next().unwrap_or("unknown").to_string(),
        None => "not found".to_string(),
    };
    render_report(&collect_checks(), &homebrew, &Redactor::from_env())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn redactor() -> Redactor {
        Redactor {
            homes: ["/home/zelda-secret-user".to_string()].into(),
            users: ["zelda-secret-user".to_string()].into(),
            hosts: ["hyrule-castle-host".to_string()].into(),
        }
    }

    #[test]
    fn redaction_replaces_paths_user_and_host() {
        let text =
            "3.9 (/home/zelda-secret-user/venv/bin/python) cd /home/zelda-secret-user && fix zelda-secret-user on hyrule-castle-host";
        let out = redactor().redact(text);
        assert_eq!(out, "3.9 (~/venv/bin/python) cd ~ && fix <user> on <host>");
    }

    #[test]
    fn redaction_respects_word_boundaries() {
        let r = Redactor { users: ["jo".to_string(), "ann".to_string()].into(), ..Redactor::default() };
        assert_eq!(r.redact("jo, ann: John joint ann2 (ann)"), "<user>, <user>: John joint ann2 (<user>)");
    }

    #[test]
    fn redaction_ignores_one_character_names() {
        let r = Redactor { users: ["a".to_string()].into(), homes: ["/".to_string()].into(), ..Redactor::default() };
        assert_eq!(r.redact("a /usr/a"), "a /usr/a");
    }

    #[test]
    fn replace_word_handles_overlaps_and_unicode() {
        assert_eq!(replace_word("aaa aa", "aa", "X"), "aaa X");
        assert_eq!(replace_word("olá bob olá", "bob", "<user>"), "olá <user> olá");
        assert_eq!(replace_word("", "x", "y"), "");
    }

    #[test]
    fn report_has_versions_checks_and_no_secrets() {
        let checks = vec![
            check("homebrew", Status::Fail, "brew not found", "Install Homebrew from https://brew.sh"),
            check("python", Status::Ok, "/home/zelda-secret-user/bin on hyrule-castle-host", "cd /home/zelda-secret-user"),
        ];
        let text = render_report(&checks, "not found", &redactor());
        assert!(text.starts_with("### brewcat diagnostics"));
        let version_line = format!("- brewcat: {VERSION}");
        for label in [version_line.as_str(), "- OS: ", "- Architecture: ", "- Window: ", "- Homebrew: not found"] {
            assert!(text.contains(label), "{label}");
        }
        assert!(text.contains("[FAIL] homebrew: brew not found") && text.contains("fix: Install Homebrew"));
        assert_eq!(text.matches("```").count(), 2); // one fenced block with the checks
        for secret in ["zelda-secret-user", "hyrule-castle-host"] {
            assert!(!text.contains(secret), "{secret}");
        }
        assert!(text.contains("~/bin on <host>"));
    }

    #[test]
    fn trusted_entries_flatten_every_list() {
        let dir = tempfile::tempdir().unwrap();
        std::fs::create_dir_all(dir.path().join(".homebrew")).unwrap();
        std::fs::write(dir.path().join(".homebrew/trust.json"), r#"{"taps": ["1985epma/brewcat", 3], "x": "nope", "y": ["a/b"]}"#).unwrap();
        // XDG_CONFIG_HOME may be set on the machine running the tests; only check the home-based path then
        if std::env::var_os("XDG_CONFIG_HOME").is_none_or(|v| v.is_empty()) {
            assert_eq!(trusted_entries(dir.path()), ["1985epma/brewcat", "a/b"]);
        }
        assert!(trusted_entries(Path::new("/definitely/not/here")).is_empty() || std::env::var_os("XDG_CONFIG_HOME").is_some());
    }

    #[test]
    fn checks_always_include_the_basics() {
        let names: Vec<String> = collect_checks().into_iter().map(|c| c.name).collect();
        for n in ["brewcat", "system", "window", "homebrew", "git"] {
            assert!(names.iter().any(|x| x == n), "{n} missing from {names:?}");
        }
    }

    #[test]
    fn status_serializes_as_the_words_the_report_uses() {
        let c = check("x", Status::Warn, "d", "h");
        assert_eq!(serde_json::to_value(&c).unwrap(), json!({"name": "x", "status": "WARN", "detail": "d", "hint": "h"}));
    }
}
