//! What an install would change: shared by `brewcat install` and the window.
//!
//! Only facts Homebrew can tell us are reported: which packages are new, which are installed already, which are
//! outdated and which extra dependencies `brew install --dry-run` says it would also install. Homebrew gives no
//! download size or install time without downloading, so none is guessed here. Nothing in this module panics:
//! when brew cannot answer, the plan says so in `notes`.

use std::collections::HashSet;
use std::sync::OnceLock;
use std::time::Duration;

use regex::Regex;

use crate::brewenv;
use crate::catalog::{Item, Kind};
use crate::sys;

/// Extra dependencies printed by [`format_plan`] before "… and N more".
pub const MAX_LISTED: usize = 30;

fn deps_header() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| Regex::new(r"^==> Would install \d+ dependenc(?:y|ies)\b").expect("valid regex"))
}

fn plausible_name() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| Regex::new(r"^[A-Za-z0-9][A-Za-z0-9@+._/-]*$").expect("valid regex"))
}

#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct Plan {
    /// `Item::full_name` of packages that are not installed yet (formulae and casks).
    pub to_install: Vec<String>,
    pub already_installed: Vec<String>,
    /// Installed AND listed by `brew outdated` (empty if unknown).
    pub outdated: Vec<String>,
    /// Extra dependencies brew would also install (from `brew install --dry-run`).
    pub extra_deps: Vec<String>,
    /// e.g. "2 cask(s): the installer may ask for your administrator password".
    pub notes: Vec<String>,
    /// Which of the names above are casks (the rest are formulae).
    pub casks: Vec<String>,
}

/// (exit code, stdout) of a read-only brew call, or None if brew could not be run in time.
fn brew(brew: &str, args: &[&str], timeout: Duration) -> Option<(i32, String)> {
    let argv = brewenv::brew_command(brew, args);
    // a plan must be quick and must not update Homebrew
    sys::run_capture(&argv, &[("HOMEBREW_NO_AUTO_UPDATE", "1")], timeout).ok().map(|c| (c.code, c.stdout))
}

/// Names of the dependencies `brew install --dry-run` lists beyond `requested`. Output looks like:
///
/// ```text
/// ==> Would install 1 formula:          (the requested packages: skipped)
/// jq 1.8.2
/// ==> Would install 1 dependency for jq:
/// oniguruma 6.9.10
/// ```
pub fn parse_dry_run<S: AsRef<str>>(text: &str, requested: &[S]) -> Vec<String> {
    let mut skip: HashSet<&str> = HashSet::new();
    for r in requested {
        let r = r.as_ref();
        skip.insert(r);
        skip.insert(r.rsplit('/').next().unwrap_or(r));
    }
    let mut deps: Vec<String> = Vec::new();
    let mut in_deps = false;
    for raw in text.lines() {
        let line = raw.trim();
        if line.starts_with("==>") {
            in_deps = deps_header().is_match(line);
            continue;
        }
        if line.is_empty() {
            in_deps = false;
        } else if in_deps {
            let name = line.split_whitespace().next().unwrap_or("");
            if plausible_name().is_match(name) && !skip.contains(name) && !deps.iter().any(|d| d == name) {
                deps.push(name.to_string());
            }
        }
    }
    deps
}

fn installed_names(brew_path: &str, kind: Kind, timeout: Duration) -> Option<HashSet<String>> {
    let flag = format!("--{}", kind.as_str());
    match brew(brew_path, &["list", &flag, "-1"], timeout) {
        Some((0, out)) => Some(out.split_whitespace().map(String::from).collect()),
        _ => None,
    }
}

/// Classify `items` and ask brew which extra dependencies they would pull in. At most five brew calls (two
/// `list`, one `outdated`, one dry run per kind), never one per package. Never panics.
pub fn build_plan(brew_path: &str, items: &[&Item], timeout: Duration) -> Plan {
    let mut notes = Vec::new();
    let installed = [Kind::Formula, Kind::Cask].map(|k| (k, installed_names(brew_path, k, timeout)));
    for (kind, names) in &installed {
        if names.is_none() && items.iter().any(|i| i.kind == *kind) {
            let k = kind.as_str();
            notes.push(format!("could not read the installed {k} list: every {k} is shown as new"));
        }
    }
    let have = |i: &Item| {
        installed
            .iter()
            .find(|(k, _)| *k == i.kind)
            .and_then(|(_, names)| names.as_ref())
            .is_some_and(|names| names.contains(&i.name) || names.contains(&i.full_name()))
    };
    let todo: Vec<&Item> = items.iter().copied().filter(|i| !have(i)).collect();
    let done: Vec<&Item> = items.iter().copied().filter(|i| have(i)).collect();

    let mut outdated = Vec::new();
    if !done.is_empty() {
        match brew(brew_path, &["outdated", "--quiet"], timeout) {
            Some((0, out)) => {
                let listed: HashSet<&str> = out.split_whitespace().collect();
                outdated = done
                    .iter()
                    .filter(|i| listed.contains(i.name.as_str()) || listed.contains(i.full_name().as_str()))
                    .map(|i| i.full_name())
                    .collect();
            }
            _ => notes.push("could not check for outdated packages".to_string()),
        }
    }

    let mut extra: Vec<String> = Vec::new();
    let mut failed = false;
    for kind in [Kind::Formula, Kind::Cask] {
        let names: Vec<String> = todo.iter().filter(|i| i.kind == kind).map(|i| i.full_name()).collect();
        if names.is_empty() {
            continue;
        }
        let mut args = vec!["install", "--dry-run"];
        if kind == Kind::Cask {
            args.push("--cask");
        }
        args.extend(names.iter().map(String::as_str));
        match brew(brew_path, &args, timeout) {
            Some((0, out)) => {
                for d in parse_dry_run(&out, &names) {
                    if !extra.contains(&d) {
                        extra.push(d);
                    }
                }
            }
            _ => failed = true,
        }
    }
    if failed {
        notes.push("could not check dependencies: brew install --dry-run failed or timed out".to_string());
    }

    let ncask = todo.iter().filter(|i| i.kind == Kind::Cask).count();
    if ncask > 0 {
        notes.push(format!("{ncask} cask(s): the installer may ask for your administrator password"));
    }
    Plan {
        to_install: todo.iter().map(|i| i.full_name()).collect(),
        already_installed: done.iter().map(|i| i.full_name()).collect(),
        outdated,
        extra_deps: extra,
        notes,
        casks: items.iter().filter(|i| i.kind == Kind::Cask).map(|i| i.full_name()).collect(),
    }
}

fn names_line(label: &str, names: &[String]) -> String {
    let mut shown = names.iter().take(MAX_LISTED).cloned().collect::<Vec<_>>().join(", ");
    if names.len() > MAX_LISTED {
        shown.push_str(&format!(", … and {} more", names.len() - MAX_LISTED));
    }
    format!("  {label}: {shown}")
}

/// Plain multi-line text (no colours): a one-line summary, then the names behind each count.
pub fn format_plan(plan: &Plan) -> String {
    let mut parts = vec![format!("{} to install", plan.to_install.len())];
    if !plan.extra_deps.is_empty() {
        let n = plan.extra_deps.len();
        parts.push(format!("{n} extra dependenc{}", if n == 1 { "y" } else { "ies" }));
    }
    if !plan.already_installed.is_empty() {
        parts.push(format!("{} already installed", plan.already_installed.len()));
    }
    if !plan.outdated.is_empty() {
        parts.push(format!("{} outdated", plan.outdated.len()));
    }
    let mut lines = vec![format!("Summary: {}.", parts.join(", "))];
    if !plan.to_install.is_empty() {
        lines.push(names_line("To install", &plan.to_install));
    }
    if !plan.extra_deps.is_empty() {
        lines.push(names_line("Also installed as dependencies", &plan.extra_deps));
    }
    if !plan.already_installed.is_empty() {
        lines.push(names_line("Already installed", &plan.already_installed));
    }
    if !plan.outdated.is_empty() {
        lines.push(names_line("Outdated (brew upgrade updates them)", &plan.outdated));
    }
    lines.extend(plan.notes.iter().map(|n| format!("  Note: {n}")));
    lines.join("\n")
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::catalog::catalog;
    use std::os::unix::fs::PermissionsExt;
    use std::path::Path;
    use std::time::Instant;

    // Output copied from a real `brew install --dry-run` (stdout); warnings go to stderr and are not parsed.
    const DRY_RUN_JQ: &str = "==> Would install 1 formula:\njq 1.8.2\n==> Downloading https://ghcr.io/v2/homebrew/core/jq/manifests/1.8.2-1\nAlready downloaded: /Users/someone/Library/Caches/Homebrew/downloads/abc--jq-1.8.2-1.bottle_manifest.json\n==> Would install 1 dependency for jq:\noniguruma 6.9.10\n";
    const DRY_RUN_MANY: &str = "==> Would install 1 formula:\nmpv 0.41.0_12\n==> Would install 3 dependencies for mpv:\njpeg-turbo      3.2.1\nlibb2           0.98.1\nlibpng          1.6.59\n";
    const DRY_RUN_CASKS: &str = "==> Would install 2 casks:\nfirefox vlc\n";

    /// A `brew` shell script; every call is appended to calls.log. `body` is the case arms for $1.
    fn make_brew(dir: &Path, body: &str) -> String {
        let script = dir.join("brew");
        let text = format!("#!/bin/sh\necho \"$@\" >> \"{}/calls.log\"\ncase \"$1\" in\n{body}\nesac\nexit 0\n", dir.display());
        std::fs::write(&script, text).unwrap();
        std::fs::set_permissions(&script, std::fs::Permissions::from_mode(0o755)).unwrap();
        script.to_string_lossy().into_owned()
    }

    fn calls(dir: &Path) -> Vec<String> {
        std::fs::read_to_string(dir.join("calls.log")).map(|t| t.lines().map(String::from).collect()).unwrap_or_default()
    }

    fn items(keys: &[&str]) -> Vec<&'static Item> {
        keys.iter().map(|k| catalog().by_key(k).unwrap_or_else(|| panic!("{k}"))).collect()
    }

    fn secs(s: f64) -> Duration {
        Duration::from_secs_f64(s)
    }

    #[test]
    fn parse_dry_run_extracts_dependencies_only() {
        assert_eq!(parse_dry_run(DRY_RUN_JQ, &["jq"]), ["oniguruma"]);
        assert_eq!(parse_dry_run(DRY_RUN_MANY, &["mpv"]), ["jpeg-turbo", "libb2", "libpng"]);
        assert!(parse_dry_run(DRY_RUN_CASKS, &["firefox", "vlc"]).is_empty());
        assert!(parse_dry_run("", &["jq"]).is_empty());
        // a requested package is never reported as its own dependency, also when requested as tap/name
        assert_eq!(parse_dry_run("==> Would install 2 dependencies for x:\nterraform 1.0\nfoo 2\n", &["hashicorp/tap/terraform"]), ["foo"]);
    }

    #[test]
    fn build_plan_classifies_and_lists_extra_dependencies() {
        let dir = tempfile::tempdir().unwrap();
        let brew = make_brew(
            dir.path(),
            &format!(
                "list) case \"$2\" in --formula) printf 'git\\ngh\\n' ;; *) printf 'iterm2\\n' ;; esac ;;\noutdated) printf 'gh\\niterm2\\n' ;;\ninstall) case \"$*\" in *--cask*) printf '{}' ;; *) cat <<'EOF2'\n{DRY_RUN_JQ}EOF2\n;; esac ;;",
                DRY_RUN_CASKS.replace('\n', "\\n")
            ),
        );
        let pl = build_plan(&brew, &items(&["formula:git", "formula:gh", "formula:jq", "cask:iterm2", "cask:warp"]), secs(60.0));
        assert_eq!(pl.to_install, ["jq", "warp"]);
        assert_eq!(pl.already_installed, ["git", "gh", "iterm2"]);
        assert_eq!(pl.outdated, ["gh", "iterm2"]);
        assert_eq!(pl.extra_deps, ["oniguruma"]);
        assert_eq!(pl.casks, ["iterm2", "warp"]);
        assert!(pl.notes.iter().any(|n| n.contains("1 cask(s)") && n.contains("administrator password")));
        let log = calls(dir.path());
        assert!(log.len() <= 5, "{log:?}"); // list x2, outdated, one dry run per kind: never one call per package
        assert!(log.contains(&"install --dry-run -- jq".to_string()), "{log:?}");
        assert!(log.contains(&"install --dry-run --cask -- warp".to_string()), "{log:?}");
    }

    #[test]
    fn build_plan_without_new_packages_makes_no_dry_run() {
        let dir = tempfile::tempdir().unwrap();
        let brew = make_brew(dir.path(), "list) printf 'git\\n' ;;");
        let pl = build_plan(&brew, &items(&["formula:git"]), secs(60.0));
        assert!(pl.to_install.is_empty() && pl.extra_deps.is_empty());
        assert_eq!(pl.already_installed, ["git"]);
        assert!(!calls(dir.path()).iter().any(|c| c.contains("--dry-run")));
    }

    #[test]
    fn failed_dry_run_gives_a_note_and_no_dependencies() {
        let dir = tempfile::tempdir().unwrap();
        let brew = make_brew(dir.path(), "list) ;;\ninstall) echo 'Error: boom' >&2; exit 1 ;;");
        let pl = build_plan(&brew, &items(&["formula:jq"]), secs(60.0));
        assert_eq!(pl.to_install, ["jq"]);
        assert!(pl.extra_deps.is_empty());
        assert!(pl.notes.iter().any(|n| n.contains("could not check dependencies")));
    }

    #[test]
    fn failed_listing_is_reported_not_raised() {
        let dir = tempfile::tempdir().unwrap();
        let brew = make_brew(dir.path(), "list) exit 1 ;;\ninstall) exit 1 ;;");
        let pl = build_plan(&brew, &items(&["formula:jq"]), secs(60.0));
        assert_eq!(pl.to_install, ["jq"]);
        assert!(pl.notes.iter().any(|n| n.contains("could not read the installed formula list")));
    }

    #[test]
    fn missing_brew_never_panics() {
        let dir = tempfile::tempdir().unwrap();
        let pl = build_plan(dir.path().join("no-such-brew").to_str().unwrap(), &items(&["formula:jq", "cask:warp"]), secs(60.0));
        assert_eq!(pl.to_install, ["jq", "warp"]);
        assert!(pl.extra_deps.is_empty());
        assert!(pl.notes.iter().any(|n| n.contains("could not check dependencies")));
    }

    #[test]
    fn timeout_is_reported_not_raised() {
        let dir = tempfile::tempdir().unwrap();
        let brew = make_brew(dir.path(), "list) ;;\ninstall) exec sleep 30 ;;");
        let start = Instant::now();
        let pl = build_plan(&brew, &items(&["formula:jq"]), secs(0.5));
        assert!(start.elapsed() < Duration::from_secs(10));
        assert!(pl.extra_deps.is_empty() && pl.notes.iter().any(|n| n.contains("could not check dependencies")));
    }

    #[test]
    fn format_plan_is_plain_text_and_invents_no_numbers() {
        let note = "1 cask(s): the installer may ask for your administrator password";
        let pl = Plan {
            to_install: vec!["jq".into(), "warp".into()],
            already_installed: vec!["git".into()],
            outdated: vec!["git".into()],
            extra_deps: vec!["oniguruma".into()],
            notes: vec![note.into()],
            casks: vec!["warp".into()],
        };
        let text = format_plan(&pl);
        assert_eq!(text.lines().next().unwrap(), "Summary: 2 to install, 1 extra dependency, 1 already installed, 1 outdated.");
        assert!(!text.contains('\x1b'));
        for name in ["jq", "warp", "oniguruma", "git", "administrator password"] {
            assert!(text.contains(name), "{name}");
        }
        for word in ["MB", "GB", "minute", "second", "~"] {
            assert!(!text.contains(word), "{word}");
        }
    }

    #[test]
    fn format_plan_truncates_long_dependency_lists() {
        let deps: Vec<String> = (0..MAX_LISTED + 5).map(|n| format!("dep{n}")).collect();
        let text = format_plan(&Plan { to_install: vec!["x".into()], extra_deps: deps.clone(), ..Plan::default() });
        assert!(text.contains("and 5 more") && !text.contains(&format!("dep{}", MAX_LISTED + 4)));
        assert_eq!(text.lines().next().unwrap(), format!("Summary: 1 to install, {} extra dependencies.", deps.len()));
    }

    #[test]
    fn format_plan_empty() {
        assert_eq!(format_plan(&Plan::default()), "Summary: 0 to install.");
    }
}
