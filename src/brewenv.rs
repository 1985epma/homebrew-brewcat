//! Homebrew and hardware detection shared by the window and the command line.

use std::path::Path;
use std::sync::OnceLock;

use crate::sys;

/// Where brew lives when it is not on `$PATH` (the Finder gives apps a minimal `$PATH`).
fn brew_candidates() -> [String; 4] {
    [
        "/opt/homebrew/bin/brew".to_string(),
        "/usr/local/bin/brew".to_string(),
        "/home/linuxbrew/.linuxbrew/bin/brew".to_string(),
        sys::home_dir().join(".linuxbrew/bin/brew").to_string_lossy().into_owned(),
    ]
}

/// The brew to use. `BREWCAT_BREW` overrides the search (a brew in an unusual place; an empty value means
/// "pretend Homebrew is not installed", which the tests use). Otherwise `$PATH`, then the usual prefixes.
pub fn find_brew() -> Option<String> {
    if let Some(forced) = std::env::var_os("BREWCAT_BREW") {
        return (!forced.is_empty()).then(|| forced.to_string_lossy().into_owned());
    }
    sys::which("brew").map(|p| p.to_string_lossy().into_owned()).or_else(|| brew_candidates().into_iter().find(|p| Path::new(p).exists()))
}

/// True on Apple Silicon hardware, even when this process runs translated under Rosetta.
pub fn apple_silicon() -> bool {
    static CACHE: OnceLock<bool> = OnceLock::new();
    *CACHE.get_or_init(|| {
        if !sys::is_mac() {
            return false;
        }
        sys::machine() == "arm64" || sys::run_text(&["/usr/sbin/sysctl", "-n", "hw.optional.arm64"], 5) == "1"
    })
}

/// [`brew_command`] with the machine facts passed in, so it can be tested anywhere.
pub fn brew_command_for<S: AsRef<str>>(brew: &str, args: &[S], silicon: bool, arch_exists: bool) -> Vec<String> {
    let args: Vec<&str> = args.iter().map(AsRef::as_ref).collect();
    let tail: Vec<String> = match args.first() {
        Some(&cmd @ ("install" | "uninstall" | "reinstall")) => {
            let opts = args[1..].iter().filter(|a| a.starts_with('-'));
            let names = args[1..].iter().filter(|a| !a.starts_with('-'));
            std::iter::once(cmd).chain(opts.copied()).chain(["--"]).chain(names.copied()).map(String::from).collect()
        }
        _ => args.iter().map(|a| a.to_string()).collect(),
    };
    if silicon && arch_exists {
        let arch = if brew.starts_with("/opt/homebrew") {
            Some("-arm64")
        } else if brew.starts_with("/usr/local") {
            Some("-x86_64")
        } else {
            None
        };
        if let Some(arch) = arch {
            return ["/usr/bin/arch", arch, brew].into_iter().map(String::from).chain(tail).collect();
        }
    }
    std::iter::once(brew.to_string()).chain(tail).collect()
}

/// Full argv to run brew. Package names go after `--` so a name can never be read as an option, and on Apple
/// Silicon brew runs in the architecture of its prefix: a plain `brew` started from a process translated by
/// Rosetta fails with "Cannot install under Rosetta 2 in ARM default prefix".
pub fn brew_command<S: AsRef<str>>(brew: &str, args: &[S]) -> Vec<String> {
    brew_command_for(brew, args, apple_silicon(), Path::new("/usr/bin/arch").exists())
}

/// The package names in a brew argument list (everything after the command that is not a flag).
pub fn package_names(args: &[String]) -> Vec<&str> {
    args.get(1..).unwrap_or(&[]).iter().filter(|a| !a.starts_with('-')).map(String::as_str).collect()
}

/// The flags in a brew argument list.
pub fn flags(args: &[String]) -> Vec<&str> {
    args.get(1..).unwrap_or(&[]).iter().filter(|a| a.starts_with('-')).map(String::as_str).collect()
}

/// Run `brew install a b c` (args = `["install", ...flags, "a", "b", "c"]`) through `run`, which executes a brew
/// argument list and returns its exit code. If the batch fails, retry package by package so one bad package
/// cannot block the others (brew skips the ones already installed). Returns the worst exit code. An error from
/// `run` (for example "cancelled") stops everything at once. The same policy is used by the window and the
/// command line.
pub fn install_with_retry<E>(
    mut run: impl FnMut(&[String]) -> Result<i32, E>,
    args: &[String],
    mut on_retry: impl FnMut(),
) -> Result<i32, E> {
    let code = run(args)?;
    let names = package_names(args);
    if code == 0 || args.first().map(String::as_str) != Some("install") || names.len() < 2 {
        return Ok(code);
    }
    on_retry();
    let flags = flags(args);
    let mut worst = i32::MIN;
    for name in names {
        let one: Vec<String> = std::iter::once("install").chain(flags.iter().copied()).chain([name]).map(String::from).collect();
        worst = worst.max(run(&one)?);
    }
    Ok(worst)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::convert::Infallible;

    fn v(parts: &[&str]) -> Vec<String> {
        parts.iter().map(|s| s.to_string()).collect()
    }

    #[test]
    fn names_go_after_double_dash() {
        assert_eq!(
            brew_command_for("/x/brew", &["install", "--cask", "foo"], false, true),
            v(&["/x/brew", "install", "--cask", "--", "foo"])
        );
        assert_eq!(brew_command_for("/x/brew", &["uninstall", "bar"], false, true), v(&["/x/brew", "uninstall", "--", "bar"]));
        assert_eq!(brew_command_for("/x/brew", &["list", "--formula", "-1"], false, true), v(&["/x/brew", "list", "--formula", "-1"]));
    }

    #[test]
    fn flags_are_moved_before_the_names() {
        assert_eq!(
            brew_command_for("/x/brew", &["install", "a", "--dry-run", "--cask", "b"], false, true),
            v(&["/x/brew", "install", "--dry-run", "--cask", "--", "a", "b"])
        );
    }

    #[test]
    fn option_looking_name_cannot_become_an_option() {
        let cmd = brew_command_for("/x/brew", &["install", "--cask", "good"], false, true);
        let dash = cmd.iter().position(|a| a == "--").unwrap();
        assert!(dash < cmd.iter().position(|a| a == "good").unwrap());
    }

    #[test]
    fn runs_native_arch_on_apple_silicon() {
        assert_eq!(
            brew_command_for("/opt/homebrew/bin/brew", &["list"], true, true)[..3],
            v(&["/usr/bin/arch", "-arm64", "/opt/homebrew/bin/brew"])[..]
        );
        assert_eq!(brew_command_for("/usr/local/bin/brew", &["list"], true, true)[..2], v(&["/usr/bin/arch", "-x86_64"])[..]);
        // no arch binary, or another prefix: plain brew
        assert_eq!(brew_command_for("/opt/homebrew/bin/brew", &["list"], true, false), v(&["/opt/homebrew/bin/brew", "list"]));
        assert_eq!(
            brew_command_for("/home/linuxbrew/.linuxbrew/bin/brew", &["list"], true, true)[0],
            "/home/linuxbrew/.linuxbrew/bin/brew"
        );
    }

    /// Fake `run(args) -> exit code`: records every call; `fail` names fail when installed alone.
    struct Runner {
        calls: Vec<Vec<String>>,
        fail: Vec<&'static str>,
        batch_fails: bool,
    }

    impl Runner {
        fn new(fail: &[&'static str], batch_fails: Option<bool>) -> Runner {
            Runner { calls: vec![], fail: fail.to_vec(), batch_fails: batch_fails.unwrap_or(!fail.is_empty()) }
        }
        fn run(&mut self, args: &[String]) -> Result<i32, Infallible> {
            self.calls.push(args.to_vec());
            let names = package_names(args);
            Ok(if names.len() > 1 { i32::from(self.batch_fails) } else { i32::from(names.iter().any(|n| self.fail.contains(n))) })
        }
    }

    #[test]
    fn retry_batch_ok_runs_once() {
        let mut r = Runner::new(&[], None);
        let mut retried = 0;
        assert_eq!(install_with_retry(|a| r.run(a), &v(&["install", "a", "b", "c"]), || retried += 1), Ok(0));
        assert_eq!(r.calls, vec![v(&["install", "a", "b", "c"])]);
        assert_eq!(retried, 0);
    }

    #[test]
    fn retry_batch_fails_then_each_package_and_worst_code() {
        let mut calls = vec![];
        let mut retried = 0;
        let res = install_with_retry::<Infallible>(
            |a| {
                calls.push(a.to_vec());
                Ok(if a.len() > 2 {
                    1
                } else {
                    match a[1].as_str() {
                        "a" => 0,
                        "b" => 3,
                        _ => 1,
                    }
                })
            },
            &v(&["install", "a", "b", "c"]),
            || retried += 1,
        );
        assert_eq!(res, Ok(3));
        assert_eq!(calls, vec![v(&["install", "a", "b", "c"]), v(&["install", "a"]), v(&["install", "b"]), v(&["install", "c"])]);
        assert_eq!(retried, 1); // announced once, before the per-package pass
    }

    #[test]
    fn retry_all_packages_ok_after_failed_batch_returns_zero() {
        let mut r = Runner::new(&[], Some(true));
        assert_eq!(install_with_retry(|a| r.run(a), &v(&["install", "a", "b"]), || {}), Ok(0));
        assert_eq!(r.calls.len(), 3);
    }

    #[test]
    fn retry_single_package_is_not_retried() {
        let mut r = Runner::new(&["a"], None);
        let mut retried = 0;
        assert_eq!(install_with_retry(|a| r.run(a), &v(&["install", "a"]), || retried += 1), Ok(1));
        assert_eq!((r.calls.len(), retried), (1, 0));
    }

    #[test]
    fn retry_only_applies_to_install() {
        for cmd in ["uninstall", "upgrade", "reinstall", "list"] {
            let mut r = Runner::new(&[], Some(true));
            let mut retried = 0;
            assert_eq!(install_with_retry(|a| r.run(a), &v(&[cmd, "a", "b"]), || retried += 1), Ok(1), "{cmd}");
            assert_eq!((r.calls.len(), retried), (1, 0), "{cmd}");
        }
    }

    #[test]
    fn retry_keeps_flags_on_every_package() {
        let mut r = Runner::new(&[], Some(true));
        let _ = install_with_retry(|a| r.run(a), &v(&["install", "--cask", "--force", "a", "b"]), || {});
        assert_eq!(
            r.calls,
            vec![
                v(&["install", "--cask", "--force", "a", "b"]),
                v(&["install", "--cask", "--force", "a"]),
                v(&["install", "--cask", "--force", "b"])
            ]
        );
    }

    #[test]
    fn an_error_from_run_stops_everything() {
        let mut calls = 0;
        let mut retried = 0;
        let res = install_with_retry(
            |_| {
                calls += 1;
                Err::<i32, &str>("cancelled")
            },
            &v(&["install", "a", "b"]),
            || retried += 1,
        );
        assert_eq!(res, Err("cancelled"));
        assert_eq!((calls, retried), (1, 0)); // no retry announcement, no second attempt
    }

    #[test]
    fn empty_arguments_do_not_panic() {
        let mut r = Runner::new(&[], None);
        assert_eq!(install_with_retry(|a| r.run(a), &[], || {}), Ok(0));
    }
}
