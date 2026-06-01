"""Tests for pipeline decorators."""

from __future__ import annotations

import time
from typing import Any

import pytest

from aereo.pipeline.decorators import retry_node


# ---------------------------------------------------------------------------
# retry_node
# ---------------------------------------------------------------------------


def test_retry_decorator_succeeds_after_failure() -> None:
    """Retry recovers when the function fails then succeeds."""
    call_count = 0

    @retry_node(max_retries=3, backoff=0.0)
    def flaky() -> str:
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise ConnectionError("fail")
        return "success"

    assert flaky() == "success"
    assert call_count == 2


def test_retry_decorator_exhausts_all_retries() -> None:
    """Retry raises the last exception when all attempts are exhausted."""
    call_count = 0

    @retry_node(max_retries=3, backoff=0.0)
    def always_fails() -> str:
        nonlocal call_count
        call_count += 1
        raise ConnectionError("fail")

    with pytest.raises(ConnectionError, match="fail"):
        always_fails()

    assert call_count == 3


def test_retry_decorator_respects_exception_filter() -> None:
    """Only the configured exception types trigger a retry."""
    call_count = 0

    @retry_node(max_retries=3, backoff=0.0, exceptions=(ValueError,))
    def raises_type_error() -> str:
        nonlocal call_count
        call_count += 1
        raise TypeError("wrong type")

    with pytest.raises(TypeError, match="wrong type"):
        raises_type_error()

    assert call_count == 1


def test_retry_decorator_allows_matching_exception() -> None:
    """Retry proceeds when the raised exception matches the filter."""
    call_count = 0

    @retry_node(max_retries=3, backoff=0.0, exceptions=(ValueError,))
    def raises_value_error() -> str:
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise ValueError("bad value")
        return "ok"

    assert raises_value_error() == "ok"
    assert call_count == 2


def test_retry_decorator_preserves_function_metadata() -> None:
    """functools.wraps keeps the original name and docstring."""

    @retry_node(max_retries=2, backoff=0.0)
    def documented() -> str:
        """My docstring."""
        return "result"

    assert documented.__name__ == "documented"
    assert documented.__doc__ == "My docstring."


def test_retry_decorator_forwards_args_and_kwargs() -> None:
    """Wrapped function receives all positional and keyword arguments."""
    received: dict[str, Any] = {}

    @retry_node(max_retries=2, backoff=0.0)
    def capture(a: int, b: str = "default") -> dict[str, Any]:
        received["a"] = a
        received["b"] = b
        return received

    result = capture(42, b="custom")
    assert result == {"a": 42, "b": "custom"}


def test_retry_decorator_single_attempt_no_retry() -> None:
    """max_retries=1 means no retries at all."""
    call_count = 0

    @retry_node(max_retries=1, backoff=0.0)
    def fails_once() -> str:
        nonlocal call_count
        call_count += 1
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        fails_once()

    assert call_count == 1


def test_retry_decorator_backoff_timing(monkeypatch: Any) -> None:
    """Backoff sleeps follow an exponential pattern."""
    sleeps: list[float] = []
    monkeypatch.setattr(time, "sleep", sleeps.append)

    @retry_node(max_retries=4, backoff=0.5)
    def flaky() -> str:
        raise ConnectionError("fail")

    with pytest.raises(ConnectionError):
        flaky()

    assert sleeps == [0.5, 1.0, 2.0]
