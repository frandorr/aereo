"""Decorators for Hamilton pipeline nodes."""

from __future__ import annotations

import functools
import time
from typing import Any, Callable, Tuple, Type


def retry_node(
    max_retries: int = 3,
    backoff: float = 1.0,
    exceptions: Tuple[Type[BaseException], ...] = (Exception,),
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator for I/O nodes (search, download) that need retries.

    Retries the wrapped function up to *max_retries* times with exponential
    backoff.  By default any ``Exception`` subclass is caught; supply a
    narrower *exceptions* tuple to retry only specific error types.

    Args:
        max_retries: Maximum number of attempts (including the first).
        backoff: Initial sleep interval in seconds.
        exceptions: Tuple of exception classes to catch and retry on.

    Returns:
        A decorator that wraps the target function with retry logic.
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exc: BaseException | None = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except exceptions as exc:
                    last_exc = exc
                    if attempt == max_retries - 1:
                        raise last_exc
                    time.sleep(backoff * (2**attempt))
            # Unreachable — loop either returns or raises.
            raise last_exc  # type: ignore[misc]

        return wrapper

    return decorator
