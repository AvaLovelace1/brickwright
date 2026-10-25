"""Tests for the low-level model execution engine."""

import multiprocessing as mp
import operator
import os
import time

import pytest

from brickwright.tools.build_execution import (
    MAX_OUTPUT,
    _worker,
    cap_output,
    create_build,
    load_build_module,
    run_in_subprocess,
)


class TestCapOutput:
    def test_text_at_the_limit_is_left_untouched(self):
        text = "a" * MAX_OUTPUT
        assert cap_output(text) == text

    def test_text_over_the_limit_is_truncated_with_a_marker(self):
        capped = cap_output("a" * (MAX_OUTPUT + 1))
        assert capped.startswith("a" * MAX_OUTPUT)
        assert capped.endswith("[truncated]")
        assert len(capped) == MAX_OUTPUT + len("\n…[truncated]")


class TestLoadBuildModule:
    def test_load_imports_the_build_module(self, make_record, valid_build):
        module = load_build_module(str(make_record(valid_build).build_path))
        assert callable(module.create_build)
        assert callable(module.run_tests)

    def test_load_reads_same_size_edits_within_one_timestamp(self, tmp_path):
        path = tmp_path / "build.py"
        path.write_text("value = 1\n")
        stamp = 1_700_000_000
        os.utime(path, (stamp, stamp))
        first = load_build_module(path)
        assert first.value == 1

        path.write_text("value = 2\n")
        os.utime(path, (stamp, stamp))
        second = load_build_module(path)
        assert second is not first
        assert second.value == 2

    def test_load_rejects_a_file_it_cannot_import(self, tmp_path):
        bad = tmp_path / "model.txt"  # no import loader for this suffix
        bad.write_text("not a module")
        with pytest.raises(ImportError, match="cannot load build file"):
            load_build_module(str(bad))


class TestRunInSubprocess:
    @pytest.mark.integration
    def test_a_result_with_a_lingering_thread_does_not_block_cleanup(self, tmp_path):
        path = tmp_path / "build.py"
        path.write_text(
            "import threading, time\n"
            "def create_build():\n"
            "    threading.Thread(target=time.sleep, args=(4,), daemon=False).start()\n"
            "    return 42\n"
        )
        started = time.monotonic()
        assert run_in_subprocess(create_build, (str(path),), timeout=1.0) == 42
        assert time.monotonic() - started < 3.0

    @pytest.mark.integration
    @pytest.mark.skipif(os.name == "nt", reason="requires POSIX signals")
    def test_timeout_kills_a_child_that_ignores_termination(self, tmp_path):
        path = tmp_path / "build.py"
        path.write_text(
            "import signal, time\n"
            "def create_build():\n"
            "    signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
            "    time.sleep(4)\n"
        )
        started = time.monotonic()
        with pytest.raises(TimeoutError, match="timed out"):
            run_in_subprocess(create_build, (str(path),), timeout=1.0)
        assert time.monotonic() - started < 3.0

    @pytest.mark.integration
    def test_returns_the_childs_result(self):
        assert run_in_subprocess(abs, (-5,), timeout=5.0) == 5

    @pytest.mark.integration
    def test_returns_a_result_larger_than_the_pipe_buffer(self):
        big = run_in_subprocess(operator.mul, ("x", 1_000_000), 10.0)
        assert len(big) == 1_000_000

    @pytest.mark.integration
    def test_times_out_when_the_child_overruns(self):
        with pytest.raises(TimeoutError, match="timed out"):
            run_in_subprocess(time.sleep, (3600,), timeout=0.3)

    @pytest.mark.integration
    def test_reports_a_child_that_exits_without_a_result(self):
        # os._exit kills the child before it can put a result on the queue.
        with pytest.raises(RuntimeError, match="exited with code 42"):
            run_in_subprocess(os._exit, (42,), timeout=5.0)


class TestWorker:
    def test_worker_puts_the_function_result_on_the_queue(self):
        result = mp.get_context("spawn").Queue()
        _worker(lambda a, b: a + b, (2, 3), result)
        assert result.get(timeout=1) == 5
