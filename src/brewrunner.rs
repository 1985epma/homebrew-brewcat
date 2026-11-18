//! Runs one brew command at a time and can stop it. No GUI types, so it is testable without a display.

use std::io::{self, Read};
use std::os::unix::process::CommandExt;
use std::process::Command;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex, MutexGuard};
use std::thread;
use std::time::{Duration, Instant};

use crate::sys::exit_code;

/// What a line of output is: brew's own output, a note from brewcat, a failure, or the command being run.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Tag {
    Out,
    Info,
    Err,
    Cmd,
}

/// Cuts a byte stream into lines the way Python's universal newlines do: `\n`, `\r\n` and a lone `\r`
/// (brew's progress bars) all end a line. Every returned line ends with `\n`.
#[derive(Default)]
pub struct LineSplitter {
    buf: Vec<u8>,
    after_cr: bool,
}

impl LineSplitter {
    fn take_line(&mut self) -> String {
        let mut line = String::from_utf8_lossy(&self.buf).into_owned();
        self.buf.clear();
        line.push('\n');
        line
    }

    pub fn push(&mut self, bytes: &[u8]) -> Vec<String> {
        let mut lines = Vec::new();
        for &b in bytes {
            if std::mem::take(&mut self.after_cr) && b == b'\n' {
                continue; // "\r\n": the line ended at the "\r" already
            }
            match b {
                b'\n' => lines.push(self.take_line()),
                b'\r' => {
                    lines.push(self.take_line());
                    self.after_cr = true;
                }
                _ => self.buf.push(b),
            }
        }
        lines
    }

    /// What is left at the end of the stream: a last line without a newline.
    pub fn finish(&mut self) -> Option<String> {
        if self.buf.is_empty() {
            return None;
        }
        let line = String::from_utf8_lossy(&self.buf).into_owned();
        self.buf.clear();
        Some(line)
    }
}

struct Running {
    pid: i32,
    exited: Arc<AtomicBool>,
}

#[derive(Default)]
struct State {
    cancelled: bool,
    running: Option<Running>,
}

/// Runs a brew argument list in a child process, streaming its output line by line.
///
/// [`run`](BrewRunner::run) blocks (call it from a worker thread). [`terminate`](BrewRunner::terminate) may be
/// called from any thread, any number of times, whether or not something is running: it stops the child and its
/// descendants, asking nicely first and killing after `grace`, and makes `run` refuse to start anything else
/// until [`reset`](BrewRunner::reset).
pub struct BrewRunner {
    grace: Duration,
    state: Mutex<State>,
}

impl Default for BrewRunner {
    fn default() -> Self {
        BrewRunner::new(Duration::from_secs(3))
    }
}

fn signal_group(pid: i32, sig: i32) {
    // SAFETY: plain syscall. The child called setsid(), so its pid is also its process group id.
    // Errors (it already exited, or the group is not ours) are fine to ignore.
    unsafe { libc::killpg(pid, sig) };
}

impl BrewRunner {
    pub fn new(grace: Duration) -> BrewRunner {
        BrewRunner { grace, state: Mutex::new(State::default()) }
    }

    fn lock(&self) -> MutexGuard<'_, State> {
        self.state.lock().unwrap_or_else(|poisoned| poisoned.into_inner())
    }

    pub fn running(&self) -> bool {
        self.lock().running.as_ref().is_some_and(|r| !r.exited.load(Ordering::SeqCst))
    }

    pub fn cancelled(&self) -> bool {
        self.lock().cancelled
    }

    /// Allow `run` again after `terminate` (a new batch of commands is starting).
    pub fn reset(&self) {
        self.lock().cancelled = false;
    }

    /// Run `argv`, send every output line to `on_line` and return the exit code (`-N` when killed by signal N,
    /// 1 when it could not start). `env` is added to the inherited environment.
    pub fn run(&self, argv: &[String], on_line: &mut dyn FnMut(Tag, &str), env: &[(String, String)]) -> i32 {
        let (mut child, mut reader, exited) = {
            let mut state = self.lock();
            if state.cancelled {
                return 1;
            }
            match Self::spawn(argv, env) {
                Ok((child, reader)) => {
                    let exited = Arc::new(AtomicBool::new(false));
                    state.running = Some(Running { pid: child.id() as i32, exited: exited.clone() });
                    (child, reader, exited)
                }
                Err(e) => {
                    drop(state);
                    on_line(Tag::Err, &format!("Error: {e}\n"));
                    return 1;
                }
            }
        };
        let mut splitter = LineSplitter::default();
        let mut chunk = [0u8; 8192];
        loop {
            match reader.read(&mut chunk) {
                Ok(0) => break,
                Ok(n) => splitter.push(&chunk[..n]).iter().for_each(|l| on_line(Tag::Out, l)),
                Err(e) if e.kind() == io::ErrorKind::Interrupted => {}
                Err(_) => break,
            }
        }
        if let Some(rest) = splitter.finish() {
            on_line(Tag::Out, &rest);
        }
        let code = child.wait().map(exit_code).unwrap_or(1);
        exited.store(true, Ordering::SeqCst);
        self.lock().running = None;
        on_line(Tag::Info, &format!("→ exit code {code}\n"));
        code
    }

    fn spawn(argv: &[String], env: &[(String, String)]) -> io::Result<(std::process::Child, io::PipeReader)> {
        let (prog, args) = argv.split_first().ok_or_else(|| io::Error::new(io::ErrorKind::InvalidInput, "empty command"))?;
        let (reader, writer) = io::pipe()?; // stdout and stderr share one pipe, so lines stay in order
        let mut cmd = Command::new(prog);
        cmd.args(args).envs(env.iter().map(|(k, v)| (k, v))).stdin(std::process::Stdio::null()).stdout(writer.try_clone()?).stderr(writer);
        // SAFETY: only async-signal-safe calls between fork and exec (setsid). Its own session, so terminate()
        // also reaches what brew spawns (curl, make...) and sudo cannot ask on our terminal.
        unsafe {
            cmd.pre_exec(|| if libc::setsid() == -1 { Err(io::Error::last_os_error()) } else { Ok(()) });
        }
        let child = cmd.spawn()?;
        drop(cmd); // closes our copies of the write end, so the reader sees EOF when the child is gone
        Ok((child, reader))
    }

    /// Stop the running command, if any: SIGTERM, then SIGKILL after the grace period.
    pub fn terminate(&self) {
        let target = {
            let mut state = self.lock();
            state.cancelled = true;
            state.running.as_ref().map(|r| (r.pid, r.exited.clone()))
        };
        let Some((pid, exited)) = target else { return };
        if exited.load(Ordering::SeqCst) {
            return;
        }
        signal_group(pid, libc::SIGTERM);
        let deadline = Instant::now() + self.grace;
        while Instant::now() < deadline {
            if exited.load(Ordering::SeqCst) {
                return;
            }
            thread::sleep(Duration::from_millis(10));
        }
        if !exited.load(Ordering::SeqCst) {
            signal_group(pid, libc::SIGKILL);
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::mpsc;

    fn sh(script: &str) -> Vec<String> {
        vec!["sh".into(), "-c".into(), script.into()]
    }

    fn collect(runner: &BrewRunner, argv: &[String], env: &[(String, String)]) -> (i32, Vec<(Tag, String)>) {
        let mut got = Vec::new();
        let code = runner.run(argv, &mut |t, s| got.push((t, s.to_string())), env);
        (code, got)
    }

    fn outs(got: &[(Tag, String)]) -> Vec<&str> {
        got.iter().filter(|(t, _)| *t == Tag::Out).map(|(_, s)| s.as_str()).collect()
    }

    /// Start `argv` on a thread; the receiver gets each output line, the handle gives the exit code.
    fn start(runner: &Arc<BrewRunner>, argv: Vec<String>) -> (mpsc::Receiver<String>, thread::JoinHandle<i32>) {
        let (tx, rx) = mpsc::channel();
        let runner = runner.clone();
        let handle = thread::spawn(move || {
            runner.run(
                &argv,
                &mut |t, s| {
                    if t == Tag::Out {
                        let _ = tx.send(s.to_string());
                    }
                },
                &[],
            )
        });
        (rx, handle)
    }

    /// True when `pid` no longer runs. A zombie counts as gone: in a container PID 1 may never reap orphans, and a
    /// killed process then stays a zombie (it still answers `kill(pid, 0)`) although it does nothing any more.
    fn process_is_gone(pid: i32) -> bool {
        // SAFETY: signal 0 only checks that the process exists.
        if unsafe { libc::kill(pid, 0) } == -1 {
            return io::Error::last_os_error().raw_os_error() == Some(libc::ESRCH);
        }
        let state = match std::fs::read_to_string(format!("/proc/{pid}/stat")) {
            // "pid (comm) S ...": the state follows the last ')'
            Ok(stat) => stat.rsplit(')').next().unwrap_or("").trim_start().chars().next().map(String::from).unwrap_or_default(),
            Err(_) => crate::sys::run_text(&["ps", "-o", "stat=", "-p", &pid.to_string()], 5), // macOS has no /proc
        };
        state.starts_with('Z')
    }

    #[test]
    fn splitter_handles_all_newline_styles() {
        let mut s = LineSplitter::default();
        let mut lines = s.push(b"one\ntwo\r\nthree\rfo");
        lines.extend(s.push(b"ur\r"));
        lines.extend(s.push(b"\nfive"));
        assert_eq!(lines, ["one\n", "two\n", "three\n", "four\n"]);
        assert_eq!(s.finish().as_deref(), Some("five"));
        assert_eq!(s.finish(), None);
    }

    #[test]
    fn splitter_keeps_multibyte_characters_split_across_chunks() {
        let mut s = LineSplitter::default();
        let bytes = "→ olá\n".as_bytes();
        let mut lines = s.push(&bytes[..2]);
        lines.extend(s.push(&bytes[2..]));
        assert_eq!(lines, ["→ olá\n"]);
    }

    #[test]
    fn streams_each_line_and_returns_exit_code() {
        let (code, got) = collect(&BrewRunner::default(), &sh("echo one; echo two; exit 3"), &[]);
        assert_eq!(code, 3);
        assert_eq!(outs(&got), ["one\n", "two\n"]);
        assert_eq!(got.last().unwrap(), &(Tag::Info, "→ exit code 3\n".to_string()));
    }

    #[test]
    fn stderr_is_merged_and_env_is_passed() {
        let env = [("BREWCAT_T".to_string(), "yes".to_string())];
        let (code, got) = collect(&BrewRunner::default(), &sh("echo $BREWCAT_T; echo oops >&2"), &env);
        assert_eq!(code, 0);
        assert_eq!(outs(&got), ["yes\n", "oops\n"]);
    }

    #[test]
    fn stdin_is_closed() {
        let (code, got) = collect(&BrewRunner::default(), &sh("cat; echo done"), &[]);
        assert_eq!((code, outs(&got)), (0, vec!["done\n"]));
    }

    #[test]
    fn missing_executable_returns_1_and_reports() {
        let runner = BrewRunner::default();
        let (code, got) = collect(&runner, &["/no/such/brew".into(), "update".into()], &[]);
        assert_eq!(code, 1);
        assert_eq!(got[0].0, Tag::Err);
        assert!(got[0].1.starts_with("Error:"));
        assert!(!runner.running());
    }

    #[test]
    fn running_flag_and_terminate_stop_a_long_sleep() {
        let runner = Arc::new(BrewRunner::default());
        assert!(!runner.running());
        let (rx, handle) = start(&runner, sh("echo up; sleep 60"));
        assert_eq!(rx.recv_timeout(Duration::from_secs(10)).unwrap(), "up\n");
        assert!(runner.running());
        let started = Instant::now();
        runner.terminate();
        let code = handle.join().unwrap();
        assert!(started.elapsed() < Duration::from_secs(10));
        assert_ne!(code, 0);
        assert!(!runner.running());
    }

    #[test]
    fn double_terminate_and_terminate_when_idle_are_safe() {
        let runner = Arc::new(BrewRunner::default());
        runner.terminate(); // nothing running
        runner.terminate();
        runner.reset();
        let (rx, handle) = start(&runner, sh("echo up; sleep 60"));
        rx.recv_timeout(Duration::from_secs(10)).unwrap();
        runner.terminate();
        runner.terminate();
        handle.join().unwrap();
        runner.terminate(); // after it finished
    }

    #[test]
    fn run_after_terminate_refuses_until_reset() {
        let runner = BrewRunner::default();
        runner.terminate();
        assert!(runner.cancelled());
        let (code, got) = collect(&runner, &sh("echo x"), &[]);
        assert_eq!((code, got.len()), (1, 0));
        runner.reset();
        let (code, got) = collect(&runner, &sh("echo x"), &[]);
        assert_eq!((code, outs(&got)), (0, vec!["x\n"]));
    }

    #[test]
    fn terminate_escalates_to_kill_when_sigterm_is_ignored() {
        let runner = Arc::new(BrewRunner::new(Duration::from_millis(300)));
        let (rx, handle) = start(&runner, sh("trap '' TERM; echo up; while true; do sleep 1; done"));
        rx.recv_timeout(Duration::from_secs(10)).unwrap();
        runner.terminate();
        assert_eq!(handle.join().unwrap(), -9); // SIGKILL
    }

    #[test]
    fn terminate_also_stops_what_the_command_spawned() {
        let dir = tempfile::tempdir().unwrap();
        let marker = dir.path().join("child.pid");
        let runner = Arc::new(BrewRunner::new(Duration::from_millis(300)));
        let (rx, handle) = start(&runner, sh(&format!("sleep 60 & echo $! > {}; echo up; wait", marker.display())));
        rx.recv_timeout(Duration::from_secs(10)).unwrap();
        let pid: i32 = std::fs::read_to_string(&marker).unwrap().trim().parse().unwrap();
        runner.terminate();
        handle.join().unwrap();
        let gone = || process_is_gone(pid);
        let end = Instant::now() + Duration::from_secs(5);
        while !gone() && Instant::now() < end {
            thread::sleep(Duration::from_millis(20));
        }
        assert!(gone(), "the grandchild survived terminate()");
    }
}
