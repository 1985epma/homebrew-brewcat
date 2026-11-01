"""BrewRunner against real tiny child processes (no brew needed)."""
import os
import sys
import threading
import time

import pytest

from brewrunner import BrewRunner

posix_only = pytest.mark.skipif(os.name != "posix", reason="process groups and sh scripts")


def collect():
    got = []
    return got, lambda tag, text: got.append((tag, text))


def wait_until(cond, timeout=10.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.02)
    return False


def start_in_thread(runner, argv, cb, env=None):
    result = []
    t = threading.Thread(target=lambda: result.append(runner.run(argv, cb, env)), daemon=True)
    t.start()
    return t, result


def test_streams_each_line_and_returns_exit_code():
    got, cb = collect()
    code = BrewRunner().run([sys.executable, "-c", "print('one'); print('two'); import sys; sys.exit(3)"], cb)
    assert code == 3
    assert [t for tag, t in got if tag == "out"] == ["one\n", "two\n"]
    assert got[-1] == ("info", "→ exit code 3\n")


def test_stderr_is_merged_and_env_is_passed():
    got, cb = collect()
    code = BrewRunner().run([sys.executable, "-c",
                             "import os, sys; print(os.environ['BREWCAT_T'], flush=True); print('oops', file=sys.stderr)"],
                            cb, env=dict(os.environ, BREWCAT_T="yes"))
    assert code == 0
    assert [t for tag, t in got if tag == "out"] == ["yes\n", "oops\n"]


def test_stdin_is_closed():
    got, cb = collect()
    code = BrewRunner().run([sys.executable, "-c", "import sys; print(repr(sys.stdin.read()))"], cb)
    assert code == 0 and ("out", "''\n") in got


def test_missing_executable_returns_1_and_reports(tmp_path):
    got, cb = collect()
    runner = BrewRunner()
    assert runner.run([str(tmp_path / "no-such-brew"), "update"], cb) == 1
    assert got and got[0][0] == "err" and got[0][1].startswith("Error:")
    assert not runner.running


def test_running_flag():
    runner = BrewRunner()
    assert not runner.running
    got, cb = collect()
    t, result = start_in_thread(runner, [sys.executable, "-c", "print('up', flush=True); import time; time.sleep(30)"], cb)
    assert wait_until(lambda: ("out", "up\n") in got)
    assert runner.running
    runner.terminate()
    t.join(10)
    assert not t.is_alive() and not runner.running


def test_terminate_stops_a_long_sleep():
    runner = BrewRunner()
    got, cb = collect()
    t, result = start_in_thread(runner, [sys.executable, "-c", "print('up', flush=True); import time; time.sleep(60)"], cb)
    assert wait_until(lambda: ("out", "up\n") in got)
    started = time.time()
    runner.terminate()
    t.join(10)
    assert not t.is_alive()
    assert time.time() - started < 10
    assert result and result[0] != 0


def test_double_terminate_and_terminate_when_idle_are_safe():
    runner = BrewRunner()
    runner.terminate()  # nothing running
    runner.terminate()
    runner.reset()
    got, cb = collect()
    t, result = start_in_thread(runner, [sys.executable, "-c", "print('up', flush=True); import time; time.sleep(60)"], cb)
    assert wait_until(lambda: ("out", "up\n") in got)
    runner.terminate()
    runner.terminate()
    t.join(10)
    assert not t.is_alive()
    runner.terminate()  # after it finished


def test_run_after_terminate_refuses_until_reset():
    runner = BrewRunner()
    runner.terminate()
    assert runner.cancelled
    got, cb = collect()
    assert runner.run([sys.executable, "-c", "print('x')"], cb) == 1 and got == []
    runner.reset()
    assert runner.run([sys.executable, "-c", "print('x')"], cb) == 0 and ("out", "x\n") in got


@posix_only
def test_terminate_escalates_to_kill_when_sigterm_is_ignored(tmp_path):
    script = tmp_path / "stubborn.sh"
    script.write_text("#!/bin/sh\ntrap '' TERM\necho up\nwhile true; do sleep 1; done\n")
    script.chmod(0o755)
    runner = BrewRunner(grace=0.3)
    got, cb = collect()
    t, result = start_in_thread(runner, [str(script)], cb)
    assert wait_until(lambda: ("out", "up\n") in got)
    runner.terminate()
    t.join(10)
    assert not t.is_alive()
    assert result == [-9]  # SIGKILL


@posix_only
def test_terminate_also_stops_what_the_command_spawned(tmp_path):
    marker = tmp_path / "child.pid"
    script = tmp_path / "parent.sh"
    script.write_text(f"#!/bin/sh\nsleep 60 &\necho $! > {marker}\necho up\nwait\n")
    script.chmod(0o755)
    runner = BrewRunner(grace=0.3)
    got, cb = collect()
    t, _ = start_in_thread(runner, [str(script)], cb)
    assert wait_until(lambda: ("out", "up\n") in got)
    pid = int(marker.read_text())
    runner.terminate()
    t.join(10)

    def gone():
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        except PermissionError:
            return False
        # a zombie (not yet reaped by init) still answers kill(pid, 0)
        return False

    assert wait_until(gone, 5)
