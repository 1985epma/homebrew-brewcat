//! Work that runs off the window's thread, and the messages it sends back (the equivalent of a queue the window
//! drains every frame). Nothing in here draws anything; the functions only need a [`Notifier`] to talk back.

use std::convert::Infallible;

use eframe::egui;
use std::path::{Path, PathBuf};
use std::sync::mpsc::Sender;
use std::time::Duration;

use crate::brewenv;
use crate::brewrunner::{BrewRunner, Tag};
use crate::catalog::{Item, Kind, catalog};
use crate::extras_core as core;
use crate::gui::state::{BatchResult, Installed, ensure_askpass};
use crate::sys;

/// What a worker tells the window.
#[derive(Debug)]
pub enum Msg {
    Log(Tag, String),
    Installed(Installed),
    /// The install plan is ready (`text` is None when it could not be computed: ask the plain question).
    PlanReady {
        title: String,
        text: Option<String>,
        cmds: Vec<Vec<String>>,
        fallback: String,
    },
    Search {
        query: String,
        found: Vec<(Kind, String)>,
    },
    Desc {
        key: String,
        text: String,
    },
    AboutInfo {
        os: String,
        brew: String,
    },
    Diagnostics(String),
    BatchDone {
        result: BatchResult,
        cancelled: bool,
    },
    Scan(Result<ScanOk, String>),
    RosettaDone,
}

/// Sends messages to the window and wakes it up.
#[derive(Clone)]
pub struct Notifier {
    tx: Sender<Msg>,
    ctx: egui::Context,
}

impl Notifier {
    pub fn new(tx: Sender<Msg>, ctx: egui::Context) -> Notifier {
        Notifier { tx, ctx }
    }

    pub fn send(&self, msg: Msg) {
        let _ = self.tx.send(msg); // the window is gone: nobody to tell
        self.ctx.request_repaint();
    }

    pub fn log(&self, tag: Tag, text: impl Into<String>) {
        self.send(Msg::Log(tag, text.into()));
    }
}

fn brew_output(brew: &str, args: &[&str], secs: u64) -> Option<String> {
    sys::run_capture(&brewenv::brew_command(brew, args), &[], Duration::from_secs(secs)).ok().map(|c| c.stdout)
}

/// `brew list` for formulae and casks. A list that cannot be read is empty.
pub fn read_installed(brew: &str) -> Installed {
    let list = |kind: &str| -> std::collections::HashSet<String> {
        brew_output(brew, &["list", &format!("--{kind}"), "-1"], 60)
            .map(|out| out.split_whitespace().map(String::from).collect())
            .unwrap_or_default()
    };
    Installed { formula: list("formula"), cask: list("cask") }
}

/// Packages of all of Homebrew whose name has every word of `q` and that are not in the curated catalog.
pub fn remote_search(brew: &str, q: &str) -> Vec<(Kind, String)> {
    let words: Vec<String> = q.to_lowercase().split_whitespace().map(String::from).collect();
    let Some(first) = words.first() else { return Vec::new() };
    let mut found = Vec::new();
    for (kind, flag) in [(Kind::Formula, "--formulae"), (Kind::Cask, "--casks")] {
        let Some(out) = brew_output(brew, &["search", flag, first], 30) else { continue };
        for name in out.split_whitespace() {
            let short = name.rsplit('/').next().unwrap_or(name);
            let lower = name.to_lowercase();
            if words.iter().all(|w| lower.contains(w.as_str())) && catalog().by_key(&format!("{}:{short}", kind.as_str())).is_none() {
                found.push((kind, name.to_string()));
            }
        }
    }
    found
}

/// The one-line description brew has for a package.
pub fn fetch_desc(brew: &str, item: &Item) -> String {
    let flag = format!("--{}", item.kind.as_str());
    let out = brew_output(brew, &["desc", &flag, &item.full_name()], 30).unwrap_or_default();
    let out = out.trim();
    match out.split_once(':') {
        Some((_, desc)) => desc.trim().to_string(),
        None if out.is_empty() => "No description available.".to_string(),
        None => out.to_string(),
    }
}

/// First line of `brew --version`, or why there is none.
pub fn brew_version(brew: Option<&str>) -> String {
    let Some(brew) = brew else { return "not found".to_string() };
    match brew_output(brew, &["--version"], 15) {
        Some(out) => out.lines().next().filter(|l| !l.is_empty()).unwrap_or("unavailable").to_string(),
        None => "unavailable".to_string(),
    }
}

fn base_env() -> Vec<(String, String)> {
    [("HOMEBREW_NO_ANALYTICS", "1"), ("HOMEBREW_NO_COLOR", "1"), ("HOMEBREW_NO_ENV_HINTS", "1"), ("NONINTERACTIVE", "1")]
        .iter()
        .map(|(k, v)| (k.to_string(), v.to_string()))
        .collect()
}

/// The environment of one brew call. Only cask installs may need `sudo`: the askpass helper is exposed to those
/// alone, together with the package(s) that ask for the password.
pub fn env_for(args: &[String], askpass: Option<&Path>) -> Vec<(String, String)> {
    let mut env = base_env();
    let installing = matches!(args.first().map(String::as_str), Some("install" | "reinstall"));
    if let (Some(askpass), true, true) = (askpass, installing, args.iter().any(|a| a == "--cask")) {
        env.push(("SUDO_ASKPASS".to_string(), askpass.to_string_lossy().into_owned()));
        env.push(("BREWCAT_PKG".to_string(), brewenv::package_names(args).join(", ")));
    }
    env
}

/// Run a batch of brew commands (blocking), logging everything. Returns what happened and whether it was stopped.
pub fn run_batch(runner: &BrewRunner, brew: &str, cfg: &Path, cmds: &[Vec<String>], notifier: &Notifier) -> (BatchResult, bool) {
    let askpass = ensure_askpass(cfg);
    let mut result = BatchResult::default();
    for args in cmds {
        if runner.cancelled() {
            break;
        }
        let _ = brewenv::install_with_retry::<Infallible>(
            |a| {
                notifier.log(Tag::Cmd, format!("\n$ brew {}\n", a.join(" ")));
                let env = env_for(a, askpass.as_deref());
                let code = runner.run(&brewenv::brew_command(brew, a), &mut |tag, text| notifier.log(tag, text), &env);
                result.record(a, code);
                Ok(code)
            },
            args,
            || {
                if !runner.cancelled() {
                    notifier.log(Tag::Info, "↻ batch failed, retrying package by package…\n");
                }
            },
        );
    }
    let cancelled = runner.cancelled();
    (result, cancelled)
}

/// Ask for the administrator password and install Rosetta 2 (macOS, Apple Silicon).
pub fn install_rosetta(notifier: &Notifier) {
    let script = "do shell script \"/usr/sbin/softwareupdate --install-rosetta --agree-to-license\" with administrator privileges";
    let argv = sys::argv(&["osascript", "-e", script]);
    let ok = match sys::run_capture(&argv, &[], Duration::from_secs(900)) {
        Ok(r) => {
            notifier.log(Tag::Out, format!("{}\n", format!("{}{}", r.stdout, r.stderr).trim()));
            r.code == 0
        }
        Err(e) => {
            notifier.log(Tag::Err, format!("Error: {e}\n"));
            false
        }
    };
    notifier.log(Tag::Info, if ok { "✓ Rosetta 2 installed.\n" } else { "✗ Rosetta 2 was not installed.\n" });
    notifier.send(Msg::RosettaDone);
}

/// One skill found by a scan.
#[derive(Debug, Clone)]
pub struct FoundSkill {
    pub folder: PathBuf,
    pub name: String,
    pub desc: String,
}

/// The result of scanning a source for skills.
#[derive(Debug)]
pub struct ScanOk {
    pub spec: String,
    /// The temporary clone the skills live in (to delete when it is not needed any more).
    pub tmp: Option<PathBuf>,
    pub commit: String,
    pub skills: Vec<FoundSkill>,
}

fn scan_in(root: &Path) -> Result<Vec<FoundSkill>, String> {
    let found = core::scan_skills(root, 4).map_err(|e| e.to_string())?;
    found
        .into_iter()
        .map(|folder| {
            let (name, desc) = core::parse_skill(&folder).map_err(|e| e.to_string())?;
            Ok(FoundSkill { folder, name, desc })
        })
        .collect()
}

/// Scan a local folder or clone a GitHub repo (shallow) and look for skills in it.
pub fn scan_source(spec: &str) -> Result<ScanOk, String> {
    let local = match spec.strip_prefix("~/") {
        Some(rest) => sys::home_dir().join(rest),
        None => PathBuf::from(spec),
    };
    if local.is_dir() {
        return Ok(ScanOk { spec: spec.to_string(), tmp: None, commit: String::new(), skills: scan_in(&local)? });
    }
    let (url, branch, sub) = core::parse_repo(spec).map_err(|e| e.to_string())?;
    let tmp = tempdir_for_clone().map_err(|e| e.to_string())?;
    let result = clone_and_scan(&url, branch.as_deref(), &sub, &tmp);
    match result {
        Ok((commit, skills)) => Ok(ScanOk { spec: spec.to_string(), tmp: Some(tmp), commit, skills }),
        Err(e) => {
            let _ = std::fs::remove_dir_all(&tmp);
            Err(e)
        }
    }
}

fn tempdir_for_clone() -> std::io::Result<PathBuf> {
    let base = std::env::temp_dir();
    for n in 0..100u32 {
        let stamp = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map(|d| d.as_nanos()).unwrap_or(0);
        let dir = base.join(format!("brewcat-skills-{}-{stamp}-{n}", std::process::id()));
        match std::fs::create_dir(&dir) {
            Ok(()) => return Ok(dir),
            Err(e) if e.kind() == std::io::ErrorKind::AlreadyExists => continue,
            Err(e) => return Err(e),
        }
    }
    Err(std::io::Error::new(std::io::ErrorKind::AlreadyExists, "no free temporary folder"))
}

fn clone_and_scan(url: &str, branch: Option<&str>, sub: &str, tmp: &Path) -> Result<(String, Vec<FoundSkill>), String> {
    let mut argv = sys::argv(&["git", "clone", "--depth", "1"]);
    if let Some(b) = branch {
        argv.extend(["--branch".to_string(), b.to_string()]);
    }
    argv.extend(["--".to_string(), url.to_string(), tmp.to_string_lossy().into_owned()]);
    let r = sys::run_capture(&argv, &[("GIT_TERMINAL_PROMPT", "0")], Duration::from_secs(180)).map_err(|e| e.to_string())?;
    if r.code != 0 {
        let err = r.stderr.trim();
        return Err(if err.is_empty() { "git clone failed".to_string() } else { err.to_string() });
    }
    let commit = core::git_head(tmp);
    let real_tmp = std::fs::canonicalize(tmp).map_err(|e| e.to_string())?;
    let root = std::fs::canonicalize(real_tmp.join(sub)).map_err(|e| e.to_string())?;
    if !root.starts_with(&real_tmp) {
        return Err("the sub-path leaves the repository".to_string()); // a "../" sub-path must not leave the clone
    }
    Ok((commit, scan_in(&root)?))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::os::unix::fs::PermissionsExt;
    use std::sync::mpsc;

    fn fake_brew(dir: &Path, body: &str) -> String {
        let script = dir.join("brew");
        std::fs::write(
            &script,
            format!("#!/bin/sh\necho \"$@\" >> \"{}/calls.log\"\ncase \"$1\" in\n{body}\nesac\nexit 0\n", dir.display()),
        )
        .unwrap();
        std::fs::set_permissions(&script, std::fs::Permissions::from_mode(0o755)).unwrap();
        script.to_string_lossy().into_owned()
    }

    fn notifier() -> (Notifier, mpsc::Receiver<Msg>) {
        let (tx, rx) = mpsc::channel();
        (Notifier::new(tx, egui::Context::default()), rx)
    }

    fn v(parts: &[&str]) -> Vec<String> {
        parts.iter().map(|s| s.to_string()).collect()
    }

    #[test]
    fn installed_lists_are_read_per_kind() {
        let dir = tempfile::tempdir().unwrap();
        let brew = fake_brew(dir.path(), "list) case \"$2\" in --formula) printf 'git\\njq\\n' ;; *) printf 'iterm2\\n' ;; esac ;;");
        let got = read_installed(&brew);
        assert_eq!(got.formula.len(), 2);
        assert!(got.formula.contains("git") && got.cask.contains("iterm2"));
        assert_eq!(read_installed("/no/such/brew"), Installed::default());
    }

    #[test]
    fn remote_search_filters_by_every_word_and_skips_the_catalog() {
        let dir = tempfile::tempdir().unwrap();
        let brew = fake_brew(
            dir.path(),
            "search) case \"$2\" in --formulae) printf '==> Formulae\\nfoo-tool\\nfoo-other\\njq\\n' ;; *) printf 'foo-app\\n' ;; esac ;;",
        );
        let got = remote_search(&brew, "foo tool");
        assert_eq!(got, [(Kind::Formula, "foo-tool".to_string())]);
        let got = remote_search(&brew, "FOO");
        assert!(got.contains(&(Kind::Cask, "foo-app".to_string())) && got.len() == 3);
        assert!(remote_search(&brew, "jq").is_empty()); // jq is in the catalog
        assert!(remote_search(&brew, "   ").is_empty());
    }

    #[test]
    fn descriptions_come_from_brew_desc() {
        let dir = tempfile::tempdir().unwrap();
        let brew = fake_brew(dir.path(), "desc) printf 'foo: A fine: tool\\n' ;;");
        let item = Item::external("foo", Kind::Formula, "Homebrew search", "x", "");
        assert_eq!(fetch_desc(&brew, &item), "A fine: tool");
        assert_eq!(fetch_desc("/no/such/brew", &item), "No description available.");
        let quiet_dir = tempfile::tempdir().unwrap();
        let quiet = fake_brew(quiet_dir.path(), "desc) printf 'no colon here\\n' ;;");
        assert_eq!(fetch_desc(&quiet, &item), "no colon here");
    }

    #[test]
    fn brew_version_is_the_first_line() {
        let dir = tempfile::tempdir().unwrap();
        let brew = fake_brew(dir.path(), "--version) printf 'Homebrew 9.9.9\\nsecond\\n' ;;");
        assert_eq!(brew_version(Some(&brew)), "Homebrew 9.9.9");
        assert_eq!(brew_version(None), "not found");
        assert_eq!(brew_version(Some("/no/such/brew")), "unavailable");
    }

    #[test]
    fn only_cask_installs_get_the_askpass_helper() {
        let helper = Path::new("/cfg/askpass.sh");
        let cask = env_for(&v(&["install", "--cask", "a", "b"]), Some(helper));
        assert!(cask.contains(&("SUDO_ASKPASS".to_string(), "/cfg/askpass.sh".to_string())));
        assert!(cask.contains(&("BREWCAT_PKG".to_string(), "a, b".to_string())));
        assert!(
            cask.contains(&("HOMEBREW_NO_ANALYTICS".to_string(), "1".to_string()))
                && cask.contains(&("NONINTERACTIVE".to_string(), "1".to_string()))
        );
        for args in [v(&["install", "a"]), v(&["update"]), v(&["uninstall", "--cask", "a"])] {
            assert!(!env_for(&args, Some(helper)).iter().any(|(k, _)| k == "SUDO_ASKPASS"), "{args:?}");
        }
        assert!(!env_for(&v(&["install", "--cask", "a"]), None).iter().any(|(k, _)| k == "SUDO_ASKPASS"));
        assert!(env_for(&v(&["reinstall", "--cask", "a"]), Some(helper)).iter().any(|(k, _)| k == "SUDO_ASKPASS"));
    }

    #[test]
    fn a_batch_retries_package_by_package_and_records_every_call() {
        let dir = tempfile::tempdir().unwrap();
        let brew = fake_brew(dir.path(), "install) for a in \"$@\"; do [ \"$a\" = bad ] && exit 1; done ;;");
        let (n, rx) = notifier();
        let runner = BrewRunner::default();
        let (result, cancelled) = run_batch(&runner, &brew, &dir.path().join("cfg"), &[v(&["install", "good", "bad"])], &n);
        assert!(!cancelled);
        assert_eq!(result.failed_installs(), ["bad"]);
        assert_eq!(result.succeeded(), ["good"]);
        let logs: Vec<String> = rx.try_iter().filter_map(|m| if let Msg::Log(_, t) = m { Some(t) } else { None }).collect();
        assert!(logs.iter().any(|l| l.contains("$ brew install good bad")));
        assert!(logs.iter().any(|l| l.contains("retrying package by package")));
    }

    #[test]
    fn a_stopped_batch_runs_nothing_and_says_so() {
        let dir = tempfile::tempdir().unwrap();
        let brew = fake_brew(dir.path(), "install) exit 0 ;;");
        let (n, _rx) = notifier();
        let runner = BrewRunner::default();
        runner.terminate();
        let (result, cancelled) = run_batch(&runner, &brew, &dir.path().join("cfg"), &[v(&["install", "a"])], &n);
        assert!(cancelled && result.calls.is_empty());
        assert!(!dir.path().join("calls.log").exists());
    }

    #[test]
    fn scanning_a_local_folder_finds_its_skills() {
        let dir = tempfile::tempdir().unwrap();
        std::fs::create_dir_all(dir.path().join("a")).unwrap();
        std::fs::write(dir.path().join("a/SKILL.md"), "---\nname: Alpha\ndescription: first\n---\n").unwrap();
        let ok = scan_source(&dir.path().to_string_lossy()).unwrap();
        assert!(ok.tmp.is_none() && ok.commit.is_empty());
        assert_eq!(ok.skills.len(), 1);
        assert_eq!((ok.skills[0].name.as_str(), ok.skills[0].desc.as_str()), ("Alpha", "first"));
    }

    #[test]
    fn scanning_rejects_options_and_exotic_transports() {
        for spec in ["--upload-pack=x", "ext::sh -c id", "file:///etc"] {
            assert!(scan_source(spec).is_err(), "{spec}");
        }
    }

    #[test]
    fn scanning_a_repo_clones_it_and_stays_inside_it() {
        if sys::which("git").is_none() {
            return;
        }
        let dir = tempfile::tempdir().unwrap();
        let repo = dir.path().join("repo");
        std::fs::create_dir_all(repo.join("skills/s1")).unwrap();
        std::fs::write(repo.join("skills/s1/SKILL.md"), "---\nname: s1\n---\n").unwrap();
        let git = |args: &[&str]| {
            sys::run_capture(
                &{
                    let mut a = sys::argv(&["git", "-C", &repo.to_string_lossy()]);
                    a.extend(args.iter().map(|s| s.to_string()));
                    a
                },
                &[],
                Duration::from_secs(30),
            )
            .unwrap()
        };
        if git(&["init", "-q"]).code != 0 {
            return;
        }
        git(&["add", "."]);
        let commit = git(&["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "x"]);
        if commit.code != 0 {
            return;
        }
        let spec = repo.to_string_lossy().into_owned();
        // a local folder is scanned in place; the clone path is exercised through clone_and_scan with a file URL
        let tmp = tempdir_for_clone().unwrap();
        let url = format!("file://{spec}");
        let cloned = clone_and_scan(&url, None, "skills", &tmp);
        if let Ok((commit, skills)) = cloned {
            assert_eq!(skills.len(), 1);
            assert_eq!(commit.len(), 40);
        }
        std::fs::remove_dir_all(&tmp).ok();
        let tmp = tempdir_for_clone().unwrap();
        assert!(clone_and_scan(&url, None, "../..", &tmp).is_err());
        std::fs::remove_dir_all(&tmp).ok();
    }
}
