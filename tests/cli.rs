//! The real `brewcat` binary, run in a sandbox: its own HOME, a PATH with a fake `brew`, nothing from this machine.

use std::fs;
use std::io::{BufRead, BufReader};
use std::os::unix::fs::PermissionsExt;
use std::path::{Path, PathBuf};
use std::process::{Command, Output, Stdio};
use std::time::{Duration, Instant};

use serde_json::Value;
use tempfile::TempDir;

const VERSION: &str = env!("CARGO_PKG_VERSION");

struct Sandbox {
    dir: TempDir,
}

struct Run {
    code: Option<i32>,
    out: String,
    err: String,
}

impl Sandbox {
    fn new() -> Sandbox {
        let dir = tempfile::tempdir().unwrap();
        fs::create_dir_all(dir.path().join("home")).unwrap();
        fs::create_dir_all(dir.path().join("bin")).unwrap();
        Sandbox { dir }
    }

    fn home(&self) -> PathBuf {
        self.dir.path().join("home")
    }

    fn path(&self, name: &str) -> PathBuf {
        self.dir.path().join(name)
    }

    /// A `brew` shell script on the PATH. Every call is appended to `calls`.
    fn fake_brew(&self, body: &str) -> &Sandbox {
        let script = format!("#!/bin/sh\necho \"$@\" >> \"{}/calls\"\n{body}\n", self.dir.path().display());
        let brew = self.dir.path().join("bin/brew");
        fs::write(&brew, script).unwrap();
        fs::set_permissions(&brew, fs::Permissions::from_mode(0o755)).unwrap();
        self
    }

    fn calls(&self) -> Vec<String> {
        fs::read_to_string(self.path("calls")).map(|t| t.lines().map(String::from).collect()).unwrap_or_default()
    }

    fn command(&self, args: &[&str]) -> Command {
        let mut cmd = Command::new(env!("CARGO_BIN_EXE_brewcat"));
        cmd.args(args)
            .env_clear()
            .env("HOME", self.home())
            .env("PATH", format!("{}:/usr/bin:/bin", self.dir.path().join("bin").display()))
            .env("BREWCAT_NO_APP", "1")
            .env("COLUMNS", "200")
            .stdin(Stdio::null());
        cmd
    }

    fn run(&self, args: &[&str]) -> Run {
        self.run_cmd(self.command(args))
    }

    fn run_cmd(&self, mut cmd: Command) -> Run {
        let o: Output = cmd.output().unwrap();
        Run {
            code: o.status.code(),
            out: String::from_utf8_lossy(&o.stdout).into_owned(),
            err: String::from_utf8_lossy(&o.stderr).into_owned(),
        }
    }

    /// Run with no Homebrew at all.
    fn run_without_brew(&self, args: &[&str]) -> Run {
        let mut cmd = self.command(args);
        cmd.env("BREWCAT_BREW", "");
        self.run_cmd(cmd)
    }
}

fn json(text: &str) -> Value {
    serde_json::from_str(text).unwrap_or_else(|e| panic!("not JSON ({e}): {text}"))
}

const QUIET_BREW: &str = r#"case "$1" in list|outdated) exit 0 ;; esac"#;

// ───────────────────────── basics ─────────────────────────

#[test]
fn version_and_help() {
    let sb = Sandbox::new();
    let r = sb.run(&["--version"]);
    assert_eq!(r.code, Some(0));
    assert!(r.out.starts_with(&format!("brewcat {VERSION}\n")), "{}", r.out);
    for args in [&["-h"][..], &["--help"], &["help"], &["search", "--help"]] {
        let r = sb.run(args);
        assert_eq!(r.code, Some(0), "{args:?}");
        assert!(r.out.contains("USAGE") && r.out.contains("brewcat doctor"), "{args:?}");
    }
}

#[test]
fn old_finder_argument_is_ignored() {
    // Without a window feature the program says so (exit 1); with it a window would open, so only check the CLI build.
    if cfg!(not(feature = "gui")) {
        let r = Sandbox::new().run(&["-psn_0_12345"]);
        assert_eq!(r.code, Some(1));
        assert!(r.err.contains("no window") && r.err.contains("brewcat doctor"), "{}", r.err);
    }
}

#[test]
fn invalid_usage_exits_2() {
    let sb = Sandbox::new();
    for args in [&["--nope"][..], &["nope"], &["search", "--profile", "bogus"], &["install"], &["export"]] {
        let r = sb.run(args);
        assert_eq!(r.code, Some(2), "{args:?}");
        assert!(r.err.contains("brewcat: error") && r.err.contains("Try `brewcat --help`"), "{args:?}: {}", r.err);
        assert!(r.out.is_empty(), "{args:?}");
    }
}

#[test]
fn search_json_and_not_found() {
    let sb = Sandbox::new();
    let r = sb.run_without_brew(&["search", "terraform", "-p", "sre", "--platform", "mac", "--json"]);
    assert_eq!(r.code, Some(0));
    let rows = json(&r.out);
    assert!(rows.as_array().unwrap().iter().any(|i| i["name"].as_str().unwrap().ends_with("terraform")));
    assert!(rows[0].get("installed").is_none(), "no brew: nothing to say about installed"); // key only with brew
    let r = sb.run_without_brew(&["search", "zzzzzz-nothing"]);
    assert_eq!(r.code, Some(1));
    assert!(r.err.contains("nothing found"));
}

#[test]
fn json_has_installed_flag_when_brew_answers() {
    let sb = Sandbox::new();
    sb.fake_brew(r#"case "$1" in list) printf 'git\n' ;; esac"#);
    let rows = json(&sb.run(&["search", "git", "--platform", "mac", "--json"]).out);
    let git = rows.as_array().unwrap().iter().find(|i| i["name"] == "git").unwrap();
    assert_eq!(git["installed"], true);
    let other = rows.as_array().unwrap().iter().find(|i| i["name"] != "git").unwrap();
    assert_eq!(other["installed"], false);
    // --installed / --not-installed filter with it
    let only = json(&sb.run(&["search", "git", "--platform", "mac", "--installed", "--json"]).out);
    assert!(!only.as_array().unwrap().is_empty() && only.as_array().unwrap().iter().all(|i| i["installed"] == true));
    let rest = json(&sb.run(&["search", "git", "--platform", "mac", "--not-installed", "--json"]).out);
    assert!(!rest.as_array().unwrap().is_empty() && rest.as_array().unwrap().iter().all(|i| i["installed"] == false));
}

#[test]
fn installed_filters_need_brew() {
    let r = Sandbox::new().run_without_brew(&["list", "--installed"]);
    assert_eq!(r.code, Some(1));
    assert!(r.err.contains("brew not found, cannot tell what is installed"));
}

#[test]
fn kits_listing_and_show() {
    let sb = Sandbox::new();
    let r = sb.run_without_brew(&["kits", "-p", "sre", "--json"]);
    assert!(json(&r.out).as_array().unwrap().iter().any(|k| k["name"] == "Terraform + AWS"));
    let r = sb.run_without_brew(&["kits", "git pro", "--json"]);
    assert_eq!(json(&r.out).as_array().unwrap().len(), 6);
    let r = sb.run_without_brew(&["kits", "no such kit"]);
    assert_eq!(r.code, Some(1));
    assert!(r.err.contains("no kit matches"));
}

#[test]
fn profiles_lists_every_slug() {
    let r = Sandbox::new().run(&["profiles"]);
    assert_eq!(r.code, Some(0));
    assert!(r.out.lines().any(|l| l.starts_with("117-labs") && l.ends_with("5 packages")), "{}", r.out);
    assert_eq!(r.out.lines().count(), 13);
}

#[test]
fn a_closed_pipe_ends_quietly() {
    let sb = Sandbox::new();
    let mut child =
        sb.command(&["list", "--platform", "mac"]).stdout(Stdio::piped()).stderr(Stdio::piped()).env("BREWCAT_BREW", "").spawn().unwrap();
    let mut first = String::new();
    BufReader::new(child.stdout.take().unwrap()).read_line(&mut first).unwrap(); // reads one line, then closes the pipe
    let out = child.wait_with_output().unwrap();
    assert!(!first.is_empty());
    assert!(!String::from_utf8_lossy(&out.stderr).contains("panicked"), "{}", String::from_utf8_lossy(&out.stderr));
}

// ───────────────────────── install ─────────────────────────

#[test]
fn install_dry_run_prints_plan_and_runs_nothing() {
    let sb = Sandbox::new();
    sb.fake_brew(
        r#"case "$1" in
  list|outdated) exit 0 ;;
  install) case "$*" in *--dry-run*) printf '==> Would install 6 formulae:\ngit gh\n==> Would install 1 dependency for git:\nlibfoo 1.0\n' ;; *) echo REAL >> "$0.real" ;; esac ;;
esac"#,
    );
    let r = sb.run(&["install", "git pro", "--dry-run", "--platform", "mac"]);
    assert_eq!(r.code, Some(0), "{}", r.err);
    assert!(r.out.contains("brew install git gh lazygit git-delta git-lfs pre-commit"), "{}", r.out);
    assert!(r.out.contains("Summary: 6 to install, 1 extra dependency.") && r.out.contains("libfoo"), "{}", r.out);
    assert!(!sb.path("bin/brew.real").exists(), "a dry run must not install");
    assert!(sb.calls().iter().all(|c| !c.starts_with("install") || c.contains("--dry-run")), "{:?}", sb.calls());
}

#[test]
fn install_dry_run_without_brew_calls_no_brew() {
    let sb = Sandbox::new();
    sb.fake_brew("echo SHOULD-NOT-RUN"); // on the PATH, but BREWCAT_BREW="" says there is none
    let r = sb.run_without_brew(&["install", "jq", "--dry-run", "--platform", "mac"]);
    assert_eq!(r.code, Some(0));
    assert!(r.out.contains("brew install jq") && !r.out.contains("Summary"), "{}", r.out);
    assert!(sb.calls().is_empty());
}

#[test]
fn install_without_brew_says_so() {
    let r = Sandbox::new().run_without_brew(&["install", "jq", "--yes", "--platform", "mac"]);
    assert_eq!(r.code, Some(1));
    assert!(r.err.contains("brew not found"));
}

#[test]
fn install_everything_already_installed() {
    let sb = Sandbox::new();
    sb.fake_brew(r#"case "$1" in list) printf 'jq\n' ;; esac"#);
    let r = sb.run(&["install", "jq", "--platform", "mac"]);
    assert_eq!(r.code, Some(0));
    assert!(r.out.contains("already installed"), "{}", r.out);
}

#[test]
fn install_without_yes_and_without_terminal_refuses() {
    let sb = Sandbox::new();
    sb.fake_brew(QUIET_BREW);
    let r = sb.run(&["install", "jq", "--platform", "mac"]);
    assert_eq!(r.code, Some(2));
    assert!(r.err.contains("--yes"), "{}", r.err);
    assert!(sb.calls().iter().all(|c| !c.contains("install -- jq")), "must not install: {:?}", sb.calls());
}

#[test]
fn install_unknown_and_ambiguous_targets() {
    let sb = Sandbox::new();
    let r = sb.run_without_brew(&["install", "nonexistent-xyz", "-n"]);
    assert_eq!(r.code, Some(1));
    assert!(r.err.contains("nothing called"));
    let r = sb.run_without_brew(&["install", "cask:obs", "-n", "--platform", "linux"]);
    assert_eq!(r.code, Some(1)); // casks do not exist on Linux
}

// Fake brew: nothing installed, dry runs are quiet; real installs fail for every package named in $FAIL.
const FAILING_BREW: &str = r#"case "$1" in
  list|outdated) exit 0 ;;
  install)
    case "$*" in *--dry-run*) exit 0 ;; esac
    for a in "$@"; do
      for f in $FAIL; do [ "$a" = "$f" ] && exit 1; done
    done
    exit 0 ;;
esac"#;

fn install_failing(sb: &Sandbox, fail: &str, args: &[&str]) -> Run {
    sb.fake_brew(FAILING_BREW);
    let mut cmd = sb.command(args);
    cmd.env("FAIL", fail);
    sb.run_cmd(cmd)
}

#[test]
fn failed_packages_are_listed_with_a_retry_command() {
    let sb = Sandbox::new();
    let r = install_failing(&sb, "gh lazygit", &["install", "git pro", "--yes", "--platform", "mac"]);
    assert_eq!(r.code, Some(1));
    assert!(r.err.contains("Failed: gh, lazygit"), "{}", r.err);
    assert!(r.err.contains("  brew install gh lazygit"), "{}", r.err);
    assert!(!r.err.split("Failed:").nth(1).unwrap().contains("git-delta"), "the ones that worked are not blamed");
    let log: Vec<String> = sb.calls().into_iter().filter(|c| !c.contains("--dry-run") && c.starts_with("install")).collect();
    assert!(log[0].starts_with("install -- git gh lazygit"), "{log:?}"); // the batch first …
    assert!(log.contains(&"install -- gh".to_string()), "{log:?}"); // … then one by one
    assert!(r.out.contains("batch failed, retrying package by package"));
}

#[test]
fn single_package_failure() {
    let sb = Sandbox::new();
    let r = install_failing(&sb, "jq", &["install", "jq", "--yes", "--platform", "mac"]);
    assert_eq!(r.code, Some(1));
    assert!(r.err.contains("Failed: jq") && r.err.contains("brew install jq"), "{}", r.err);
}

#[test]
fn failed_casks_are_retried_with_the_cask_flag() {
    let sb = Sandbox::new();
    let r = install_failing(&sb, "warp", &["install", "cask:warp", "--yes", "--platform", "mac"]);
    assert_eq!(r.code, Some(1));
    assert!(r.err.contains("brew install --cask warp"), "{}", r.err);
}

#[test]
fn mixed_kinds_get_one_retry_line_each() {
    let sb = Sandbox::new();
    let r = install_failing(&sb, "jq visual-studio-code", &["install", "Web Full-Stack", "--yes", "--platform", "mac"]);
    assert_eq!(r.code, Some(1));
    assert!(r.err.contains("Failed: jq, visual-studio-code"), "{}", r.err);
    assert!(r.err.contains("  brew install jq\n") && r.err.contains("  brew install --cask visual-studio-code\n"), "{}", r.err);
}

#[test]
fn success_prints_no_failure_summary() {
    let sb = Sandbox::new();
    let r = install_failing(&sb, "", &["install", "jq", "--yes", "--platform", "mac"]);
    assert_eq!(r.code, Some(0));
    assert!(!r.err.contains("Failed"), "{}", r.err);
}

// ───────────────────────── Ctrl-C ─────────────────────────

fn wait_for(path: &Path) {
    let deadline = Instant::now() + Duration::from_secs(20);
    while !path.exists() && Instant::now() < deadline {
        std::thread::sleep(Duration::from_millis(50));
    }
    assert!(path.exists(), "the fake brew install never started");
}

#[test]
fn ctrl_c_during_install_cancels_without_a_panic_or_a_retry() {
    let sb = Sandbox::new();
    let pids = sb.path("pids");
    // Stands in for brew: `list`/`outdated` print nothing (nothing installed); `install --dry-run` (the plan) answers at
    // once; a real `install` records its pid and then blocks.
    sb.fake_brew(&format!(
        r#"case "$1" in
  list|outdated) exit 0 ;;
  install)
    case "$*" in *--dry-run*) exit 0 ;; esac
    echo $$ >> "{}"; exec sleep 60 ;;
esac"#,
        pids.display()
    ));
    // "git pro" is a multi-package kit, so a failed batch WOULD trigger the one-by-one retry.
    let child =
        sb.command(&["install", "git pro", "--yes", "--platform", "mac"]).stdout(Stdio::piped()).stderr(Stdio::piped()).spawn().unwrap();
    wait_for(&pids);
    let brew_pid: i32 = fs::read_to_string(&pids).unwrap().split_whitespace().next().unwrap().parse().unwrap();
    // A terminal delivers Ctrl-C to the whole foreground group; signal brewcat and its brew child one by one.
    // SAFETY: plain syscalls on processes this test started.
    unsafe {
        libc::kill(child.id() as i32, libc::SIGINT);
        libc::kill(brew_pid, libc::SIGINT);
    }
    let out = child.wait_with_output().unwrap();
    let (stdout, stderr) = (String::from_utf8_lossy(&out.stdout), String::from_utf8_lossy(&out.stderr));
    assert!(!stderr.contains("panicked"), "{stderr}");
    assert!(stderr.contains("Cancelled."), "{stderr}");
    assert_eq!(out.status.code(), Some(130));
    assert!(!stdout.contains("retrying"), "{stdout}");
    assert_eq!(fs::read_to_string(&pids).unwrap().split_whitespace().count(), 1, "brew install must not be started again after Ctrl-C");
}

#[test]
fn ctrl_c_stops_brew_even_when_only_brewcat_gets_the_signal() {
    let sb = Sandbox::new();
    let pids = sb.path("pids");
    sb.fake_brew(&format!(
        r#"case "$1" in
  list|outdated) exit 0 ;;
  install)
    case "$*" in *--dry-run*) exit 0 ;; esac
    echo $$ >> "{}"; exec sleep 60 ;;
esac"#,
        pids.display()
    ));
    let child = sb.command(&["install", "jq", "--yes", "--platform", "mac"]).stdout(Stdio::null()).stderr(Stdio::piped()).spawn().unwrap();
    wait_for(&pids);
    let brew_pid: i32 = fs::read_to_string(&pids).unwrap().trim().parse().unwrap();
    // SAFETY: plain syscall on a process this test started.
    unsafe { libc::kill(child.id() as i32, libc::SIGINT) };
    let out = child.wait_with_output().unwrap();
    assert_eq!(out.status.code(), Some(130));
    // SAFETY: signal 0 only checks that the process exists.
    let end = Instant::now() + Duration::from_secs(5);
    let gone = || unsafe { libc::kill(brew_pid, 0) } == -1;
    while !gone() && Instant::now() < end {
        std::thread::sleep(Duration::from_millis(50));
    }
    assert!(gone(), "brew was left running");
}

// ───────────────────────── export ─────────────────────────

#[test]
fn export_to_stdout_and_file() {
    let sb = Sandbox::new();
    let r = sb.run_without_brew(&["export", "git pro", "--platform", "mac"]);
    assert_eq!(r.code, Some(0));
    assert!(r.out.contains("brew \"git\""));
    let target = sb.path("Brewfile");
    let r = sb.run_without_brew(&["export", "jq", "cask:obs", "--platform", "mac", "-o", target.to_str().unwrap()]);
    assert_eq!(r.code, Some(0));
    assert_eq!(fs::read_to_string(&target).unwrap(), "brew \"jq\"\ncask \"obs\"\n");
    assert!(r.err.contains("Wrote 2 package(s)"));
}

#[test]
fn cask_is_not_offered_on_linux() {
    let r = Sandbox::new().run_without_brew(&["export", "cask:obs", "--platform", "linux"]);
    assert_eq!(r.code, Some(1));
    assert!(r.err.contains("linux"), "{}", r.err);
}

// ───────────────────────── doctor ─────────────────────────

#[test]
fn doctor_json_shape_and_exit_code() {
    let sb = Sandbox::new();
    let r = sb.run_without_brew(&["doctor", "--json"]);
    let data = json(&r.out);
    assert_eq!(data["version"], VERSION);
    for key in ["name", "status", "detail", "hint"] {
        assert!(data["checks"][0].get(key).is_some(), "{key}");
    }
    // no brew: the homebrew check fails, so the exit code is 1 and "ok" is false
    assert_eq!(r.code, Some(1));
    assert_eq!(data["ok"], false);
    let homebrew = data["checks"].as_array().unwrap().iter().find(|c| c["name"] == "homebrew").unwrap();
    assert_eq!(homebrew["status"], "FAIL");
}

#[test]
fn doctor_text_has_status_tags_and_hints() {
    let r = Sandbox::new().run_without_brew(&["doctor"]);
    assert_eq!(r.code, Some(1));
    assert!(r.out.contains("[FAIL] homebrew") && r.out.contains("→ Install Homebrew from https://brew.sh"), "{}", r.out);
    assert!(r.out.contains("Problems found (1 failure(s)"), "{}", r.out);
}

#[test]
fn doctor_report_leaks_no_home_user_or_environment() {
    let sb = Sandbox::new();
    let home = sb.path("home/zelda-secret-user");
    fs::create_dir_all(&home).unwrap();
    let mut cmd = sb.command(&["doctor", "--report", "--json"]); // --report wins over --json
    cmd.env("HOME", &home)
        .env("USER", "zelda-secret-user")
        .env("LOGNAME", "zelda-secret-user")
        .env("SECRET_TOKEN", "hunter2-token-value")
        .env("BREWCAT_BREW", "");
    let r = sb.run_cmd(cmd);
    assert_eq!(r.code, Some(0));
    assert!(r.out.starts_with("### brewcat diagnostics") && !r.out.trim_start().starts_with('{'), "{}", r.out);
    for secret in [home.to_str().unwrap(), sb.dir.path().to_str().unwrap(), "zelda-secret-user", "hunter2", "SECRET_TOKEN"] {
        assert!(!r.out.contains(secret), "{secret} leaked:\n{}", r.out);
    }
    assert!(r.out.contains(&format!("- brewcat: {VERSION}")) && r.out.contains("- Homebrew: not found"), "{}", r.out);
    assert!(r.out.contains("[FAIL] homebrew: brew not found") && r.out.contains("fix: Install Homebrew"), "{}", r.out);
    assert_eq!(r.out.matches("```").count(), 2);
}

#[test]
fn doctor_reports_an_untrusted_tap() {
    let sb = Sandbox::new();
    sb.fake_brew(&format!(
        r#"case "$1" in --version) echo "Homebrew 9.9.9" ;; --repository) echo "{}/repo" ;; esac"#,
        sb.dir.path().display()
    ));
    fs::create_dir_all(sb.path("repo/Library/Taps/1985epma/homebrew-brewcat")).unwrap();
    let r = sb.run(&["doctor"]);
    assert!(r.out.contains("[WARN] brewcat tap") && r.out.contains("brew trust 1985epma/brewcat"), "{}", r.out);
    fs::create_dir_all(sb.home().join(".homebrew")).unwrap();
    fs::write(sb.home().join(".homebrew/trust.json"), r#"{"taps": ["1985epma/brewcat"]}"#).unwrap();
    let r = sb.run(&["doctor"]);
    assert!(r.out.contains("[OK  ] brewcat tap") && r.out.contains("Homebrew 9.9.9"), "{}", r.out);
}

// ───────────────────────── macOS app bundle ─────────────────────────

#[test]
fn install_app_follows_the_platform() {
    let sb = Sandbox::new();
    let r = sb.run(&["--install-app"]);
    assert_eq!(r.code, Some(0), "{}", r.err);
    if cfg!(target_os = "macos") {
        assert!(r.out.contains("Created ~/Applications/brewcat.app"));
        assert!(sb.home().join("Applications/brewcat.app/Contents/MacOS/brewcat").is_file());
        assert!(sb.home().join("Applications/brewcat.app/Contents/Resources/brewcat.icns").is_file());
    } else {
        assert!(r.out.contains("only needed on macOS"));
    }
}
