"""Tests for LocalExecutor.shutdown memory-reclaim behaviour."""

from unittest.mock import MagicMock, patch

from aereo.executors import LocalExecutor


def _mock_loky_pool() -> MagicMock:
    pool = MagicMock()
    return pool


def test_shutdown_sequential_does_not_touch_loky_pool():
    """A sequential executor never spawned workers, so the pool is left alone."""
    executor = LocalExecutor(workers=1)
    pool = _mock_loky_pool()
    with patch(
        "joblib.externals.loky.get_reusable_executor", return_value=pool
    ) as get_executor:
        executor.shutdown()
    get_executor.assert_not_called()
    pool.shutdown.assert_not_called()


def test_shutdown_after_parallel_run_kills_loky_pool():
    """After dispatching parallel work, shutdown terminates the reusable pool."""
    executor = LocalExecutor(workers=2)
    executor._ran_parallel = True
    pool = _mock_loky_pool()
    with patch("joblib.externals.loky.get_reusable_executor", return_value=pool):
        executor.shutdown()
    pool.shutdown.assert_called_once_with(wait=True, kill_workers=True)


def test_shutdown_threaded_executor_does_not_touch_loky_pool():
    """A threading-backend executor never used the loky pool."""
    executor = LocalExecutor(workers=2, use_threads=True)
    executor._ran_parallel = True
    pool = _mock_loky_pool()
    with patch(
        "joblib.externals.loky.get_reusable_executor", return_value=pool
    ) as get_executor:
        executor.shutdown()
    get_executor.assert_not_called()
    pool.shutdown.assert_not_called()


def test_shutdown_reclaims_main_process_memory():
    """shutdown triggers gc and malloc_trim so freed arenas return to the OS."""
    executor = LocalExecutor(workers=1)
    with (
        patch("gc.collect") as gc_collect,
        patch("ctypes.CDLL") as cdll,
    ):
        executor.shutdown()
    gc_collect.assert_called_once()
    cdll.assert_called_once_with("libc.so.6")
    cdll.return_value.malloc_trim.assert_called_once_with(0)


def test_shutdown_tolerates_non_glibc_platform():
    """A missing libc (musl, macOS) must not break shutdown."""
    executor = LocalExecutor(workers=1)
    with patch("ctypes.CDLL", side_effect=OSError("no libc")):
        executor.shutdown()  # must not raise
