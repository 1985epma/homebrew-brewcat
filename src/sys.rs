//! Small OS helpers shared by the command line and the window: home and config folders, `which`, host and OS
//! descriptions, and running a command to completion with a timeout. No GUI types in here.

use std::io::{self, Read};
use std::os::unix::fs::PermissionsExt;
use std::os::unix::process::{CommandExt, ExitStatusExt};
use std::path::{Path, PathBuf};
use std::process::{Command, ExitStatus, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::thread;
use std::time::{Duration, Instant};

/// True when this build runs on macOS.
pub const fn is_mac() -> bool {
    cfg!(target_os = "macos")
}

/// The home directory. `$HOME` wins (tests and containers set it), then the passwd entry.
pub fn home_dir() -> PathBuf {
    std::env::var_os("HOME").filter(|h| !h.is_empty()).map(PathBuf::from).or_else(std::env::home_dir).unwrap_or_else(|| PathBuf::from("/"))
}

/// Where brewcat keeps its small per-user files (askpass helper, one-time flags) under `home`.
pub fn config_dir_in(home: &Path) -> PathBuf {
    if is_mac() { home.join("Library/Application Support/brewcat") } else { home.join(".local/share/brewcat") }
}

/// [`config_dir_in`] for the real home directory.
pub fn config_dir() -> PathBuf {
    config_dir_in(&home_dir())
}

fn is_executable_file(p: &Path) -> bool {
    p.metadata().map(|m| m.is_file() && m.permissions().mode() & 0o111 != 0).unwrap_or(false)
}

/// The first executable called `name` on `$PATH`.
pub fn which(name: &str) -> Option<PathBuf> {
    if name.contains('/') {
        let p = PathBuf::from(name);
        return is_executable_file(&p).then_some(p);
    }
    let path = std::env::var_os("PATH")?;
    std::env::split_paths(&path).map(|d| d.join(name)).find(|p| is_executable_file(p))
}

/// What `uname -m` would say for this process: `arm64` on Apple Silicon, `aarch64` on Linux.
pub fn machine() -> &'static str {
    match (std::env::consts::ARCH, is_mac()) {
        ("aarch64", true) => "arm64",
        (arch, _) => arch,
    }
}

/// The host name, if the system tells us.
pub fn hostname() -> Option<String> {
    let mut buf = vec![0u8; 256];
    // SAFETY: the buffer is valid for `buf.len()` bytes and gethostname NUL-terminates unless it truncates.
    let rc = unsafe { libc::gethostname(buf.as_mut_ptr().cast(), buf.len()) };
    if rc != 0 {
        return None;
    }
    let end = buf.iter().position(|&b| b == 0).unwrap_or(buf.len());
    let name = String::from_utf8_lossy(&buf[..end]).trim().to_string();
    (!name.is_empty()).then_some(name)
}

/// Set by the command line when the user presses Ctrl-C: commands run by [`run_capture`] stop at once.
pub static INTERRUPTED: AtomicBool = AtomicBool::new(false);

pub fn interrupted() -> bool {
    INTERRUPTED.load(Ordering::SeqCst)
}

/// What a finished command produced. `code` is `-N` when the command was killed by signal N.
#[derive(Debug, Clone)]
pub struct Captured {
    pub code: i32,
    pub stdout: String,
    pub stderr: String,
}

/// Exit code of `status` the way a shell and Python's subprocess report it: the code, or `-signal`.
pub fn exit_code(status: ExitStatus) -> i32 {
    status.code().unwrap_or_else(|| -status.signal().unwrap_or(1))
}

/// Run `argv` to completion, capturing stdout and stderr. stdin is closed. `envs` are added to the inherited
/// environment. When `timeout` passes, the command and everything it started are killed and the error kind is
/// `TimedOut`; the same happens with kind `Interrupted` after Ctrl-C ([`INTERRUPTED`]). Fails with the OS error
/// when the command cannot be started.
pub fn run_capture(argv: &[String], envs: &[(&str, &str)], timeout: Duration) -> io::Result<Captured> {
    let (prog, args) = argv.split_first().ok_or_else(|| io::Error::new(io::ErrorKind::InvalidInput, "empty command"))?;
    let mut child = Command::new(prog)
        .args(args)
        .envs(envs.iter().copied())
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .process_group(0) // its own group, so a timeout can stop what the command spawned too
        .spawn()?;
    let reader = |mut pipe: Box<dyn Read + Send>| {
        thread::spawn(move || {
            let mut buf = Vec::new();
            let _ = pipe.read_to_end(&mut buf);
            String::from_utf8_lossy(&buf).into_owned()
        })
    };
    let out = reader(Box::new(child.stdout.take().expect("piped")));
    let err = reader(Box::new(child.stderr.take().expect("piped")));
    let deadline = Instant::now() + timeout;
    let status = loop {
        if let Some(status) = child.try_wait()? {
            break status;
        }
        let stop = if interrupted() {
            Some(io::ErrorKind::Interrupted)
        } else if Instant::now() >= deadline {
            Some(io::ErrorKind::TimedOut)
        } else {
            None
        };
        if let Some(kind) = stop {
            // SAFETY: plain syscall; the group id is our child's pid because of process_group(0).
            unsafe { libc::killpg(child.id() as i32, libc::SIGKILL) };
            let _ = child.wait();
            return Err(io::Error::new(kind, "command stopped"));
        }
        thread::sleep(Duration::from_millis(4));
    };
    let join = |h: thread::JoinHandle<String>| h.join().unwrap_or_default();
    Ok(Captured { code: exit_code(status), stdout: join(out), stderr: join(err) })
}

/// `argv` as owned strings, for callers that build commands from `&str` literals.
pub fn argv(parts: &[&str]) -> Vec<String> {
    parts.iter().map(|s| s.to_string()).collect()
}

/// stdout of a quick read-only command, trimmed; empty when it fails or takes longer than `secs`.
pub fn run_text(parts: &[&str], secs: u64) -> String {
    run_capture(&argv(parts), &[], Duration::from_secs(secs)).map(|c| c.stdout.trim().to_string()).unwrap_or_default()
}

/// Human-readable OS name, version and CPU architecture (flags Rosetta translation).
pub fn os_description() -> String {
    let machine = machine();
    if is_mac() {
        let version = run_text(&["/usr/bin/sw_vers", "-productVersion"], 5);
        let name = format!("macOS {}", if version.is_empty() { "?" } else { &version });
        let translated = run_text(&["/usr/sbin/sysctl", "-n", "hw.optional.arm64"], 5) == "1";
        if machine == "x86_64" && translated {
            return format!("{name} ({machine}, Apple Silicon running under Rosetta)");
        }
        let arch = if machine == "arm64" { "Apple Silicon, arm64" } else { machine };
        return format!("{name} ({arch})");
    }
    let name = ["/etc/os-release", "/usr/lib/os-release"]
        .iter()
        .filter_map(|p| std::fs::read_to_string(p).ok())
        .find_map(|text| parse_pretty_name(&text))
        .unwrap_or_else(|| {
            let kernel = run_text(&["uname", "-sr"], 5);
            if kernel.is_empty() { "Linux".to_string() } else { kernel }
        });
    format!("{name} ({machine})")
}

/// `PRETTY_NAME` from an os-release file.
pub fn parse_pretty_name(text: &str) -> Option<String> {
    text.lines().find_map(|line| {
        let value = line.strip_prefix("PRETTY_NAME=")?;
        let value = value.trim().trim_matches(|c| c == '"' || c == '\'');
        (!value.is_empty()).then(|| value.to_string())
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn captures_output_and_exit_code() {
        let r = run_capture(&argv(&["sh", "-c", "echo hi; echo oops >&2; exit 3"]), &[], Duration::from_secs(10)).unwrap();
        assert_eq!((r.code, r.stdout.as_str(), r.stderr.as_str()), (3, "hi\n", "oops\n"));
    }

    #[test]
    fn passes_extra_environment_and_closes_stdin() {
        let r = run_capture(&argv(&["sh", "-c", "echo $BREWCAT_T; cat"]), &[("BREWCAT_T", "yes")], Duration::from_secs(10)).unwrap();
        assert_eq!(r.stdout, "yes\n");
    }

    #[test]
    fn timeout_kills_the_command_and_what_it_spawned() {
        let start = Instant::now();
        let err = run_capture(&argv(&["sh", "-c", "sleep 30 & wait"]), &[], Duration::from_millis(300)).unwrap_err();
        assert_eq!(err.kind(), io::ErrorKind::TimedOut);
        assert!(start.elapsed() < Duration::from_secs(10));
    }

    #[test]
    fn missing_command_is_an_error_not_a_panic() {
        assert!(run_capture(&argv(&["/no/such/brew"]), &[], Duration::from_secs(5)).is_err());
        assert!(run_capture(&[], &[], Duration::from_secs(5)).is_err());
    }

    #[test]
    fn signal_exit_is_negative() {
        let r = run_capture(&argv(&["sh", "-c", "kill -9 $$"]), &[], Duration::from_secs(10)).unwrap();
        assert_eq!(r.code, -9);
    }

    #[test]
    fn which_finds_sh_and_rejects_nonsense() {
        assert!(which("sh").is_some());
        assert!(which("definitely-not-a-command-xyz").is_none());
    }

    #[test]
    fn pretty_name_is_parsed() {
        assert_eq!(parse_pretty_name("NAME=x\nPRETTY_NAME=\"Ubuntu 24.04 LTS\"\n").as_deref(), Some("Ubuntu 24.04 LTS"));
        assert_eq!(parse_pretty_name("NAME=x\n"), None);
    }

    #[test]
    fn config_dir_follows_the_platform() {
        let dir = config_dir_in(Path::new("/h"));
        assert!(dir.ends_with(if is_mac() { "Library/Application Support/brewcat" } else { ".local/share/brewcat" }));
    }
}
