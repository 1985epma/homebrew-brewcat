"""Runs one brew command at a time and can stop it (no tkinter import, so it is testable without a display)."""
from __future__ import annotations

import os
import signal
import subprocess
import threading
from typing import Callable, Dict, Optional, Sequence

# on_line(tag, text): tag is "out" for a line of brew output, "info" for our own notes, "err" for failures.
LineCallback = Callable[[str, str], None]


class BrewRunner:
    """Runs a brew argument list in a child process, streaming its output line by line.

    run() blocks (call it from a worker thread). terminate() may be called from any thread, any number of
    times, whether or not something is running: it stops the child and its descendants, asking nicely first and
    killing after `grace` seconds, and makes run() refuse to start anything else until reset()."""

    def __init__(self, grace: float = 3.0) -> None:
        self.grace = grace
        self._lock = threading.Lock()
        self._proc: Optional["subprocess.Popen[str]"] = None
        self._cancelled = False

    @property
    def running(self) -> bool:
        with self._lock:
            return self._proc is not None and self._proc.poll() is None

    @property
    def cancelled(self) -> bool:
        return self._cancelled

    def reset(self) -> None:
        """Allow run() again after terminate() (a new batch of commands is starting)."""
        self._cancelled = False

    def run(self, argv: Sequence[str], on_line: LineCallback, env: Optional[Dict[str, str]] = None) -> int:
        """Run argv, send every output line to on_line and return the exit code (1 if it could not start)."""
        with self._lock:
            if self._cancelled:
                return 1
            try:
                # Its own session/process group, so terminate() also reaches what brew spawns (curl, make...).
                proc = subprocess.Popen(list(argv), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                        stdin=subprocess.DEVNULL, text=True, errors="replace", env=env,
                                        start_new_session=os.name == "posix")
            except OSError as exc:
                on_line("err", f"Error: {exc}\n")
                return 1
            self._proc = proc
        try:
            if proc.stdout is not None:
                for line in proc.stdout:
                    on_line("out", line)
            code = proc.wait()
        finally:
            if proc.stdout is not None:
                proc.stdout.close()
            with self._lock:
                self._proc = None
        on_line("info", f"→ exit code {code}\n")
        return code

    def terminate(self) -> None:
        """Stop the running command, if any: SIGTERM, then SIGKILL after the grace period."""
        with self._lock:
            self._cancelled = True
            proc = self._proc
        if proc is None or proc.poll() is not None:
            return
        self._signal(proc, signal.SIGTERM)
        try:
            proc.wait(timeout=self.grace)
        except subprocess.TimeoutExpired:
            if proc.poll() is None:
                self._signal(proc, getattr(signal, "SIGKILL", signal.SIGTERM))

    @staticmethod
    def _signal(proc: "subprocess.Popen[str]", sig: int) -> None:
        try:
            if os.name == "posix":
                os.killpg(proc.pid, sig)  # pid == pgid because of start_new_session
            elif sig == signal.SIGTERM:
                proc.terminate()
            else:
                proc.kill()
        except (ProcessLookupError, PermissionError):
            pass  # it exited in the meantime
