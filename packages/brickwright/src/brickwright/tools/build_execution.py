"""Import a build.py module and run a callable in a child process."""

from __future__ import annotations

import importlib.util
import multiprocessing as mp
import queue
import sys
import time
from collections.abc import Callable
from multiprocessing.queues import Queue
from pathlib import Path
from typing import Any, TypeVar

T = TypeVar("T")

# Synthetic module name for the loaded build file.
_MODULE_NAME = "_brickwright_build"

# Cap captured output so a runaway print loop can't flood the model's context.
MAX_OUTPUT = 10_000

# How often a waiting parent checks whether its child has died.
_POLL_INTERVAL = 0.1


def cap_output(text: str) -> str:
    """Truncate ``text`` to the output cap, marking where it was cut."""
    if len(text) <= MAX_OUTPUT:
        return text
    return text[:MAX_OUTPUT] + "\n…[truncated]"


def load_build_module(build_path: str | Path, source: str | None = None) -> Any:
    """Import a fresh module, optionally from an already captured source snapshot."""
    spec = importlib.util.spec_from_file_location(_MODULE_NAME, build_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load build file {build_path!r}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[_MODULE_NAME] = module
    # Same-size edits within a second can still match a timestamp-based .pyc.
    exec(
        compile(
            source if source is not None else Path(build_path).read_bytes(),
            str(build_path),
            "exec",
        ),
        module.__dict__,
    )
    return module


def create_build(build_path: str | Path) -> Any:
    """Load ``build_path`` and return what its ``create_build()`` builds."""
    return load_build_module(build_path).create_build()


def run_guarded(
    fn: Callable,
    args: tuple[Any, ...],
    timeout: float,
    on_failure: Callable[[Exception], T],
) -> T:
    """Run ``fn`` in a child process, turning a timeout or crash into a report.

    ``on_failure`` builds the caller's own failure report from the exception.
    """
    try:
        return run_in_subprocess(fn, args, timeout)
    except (TimeoutError, RuntimeError) as e:
        return on_failure(e)


def run_in_subprocess(fn: Callable, args: tuple[Any, ...], timeout: float) -> Any:
    """Run ``fn`` in a child process and return its result.

    Raises ``TimeoutError`` if the child overruns ``timeout``
    and ``RuntimeError`` if it exits without producing a result.
    """
    ctx = mp.get_context("spawn")
    result: Queue = ctx.Queue()
    proc = ctx.Process(target=_worker, args=(fn, args, result))
    proc.start()
    try:
        # Drain the queue before joining: a child blocks on exit until a
        # result bigger than the pipe buffer has been read.
        deadline = time.monotonic() + timeout
        while proc.is_alive() and time.monotonic() < deadline:
            try:
                return result.get(timeout=_POLL_INTERVAL)  # pragma: no mutate
            except queue.Empty:
                continue
        if proc.is_alive():
            raise TimeoutError(f"timed out after {timeout}s")
        try:
            # Short timeout covers the queue's flush
            return result.get(timeout=0.5)  # pragma: no mutate -- null deadlocks mutmut
        except queue.Empty:
            raise RuntimeError(f"exited with code {proc.exitcode}")
    finally:
        proc.join(timeout=_POLL_INTERVAL)
        if proc.is_alive():
            proc.terminate()
            proc.join(timeout=_POLL_INTERVAL)
            if proc.is_alive():
                proc.kill()
                proc.join()
        result.close()
        proc.close()


def _worker(fn: Callable, args: tuple[Any, ...], result: Queue) -> None:
    result.put(fn(*args))
