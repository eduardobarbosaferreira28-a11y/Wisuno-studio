"""
retry_utils.py
==============
Small, dependency-free retry helper shared by the carousel pipeline (CLI) and the
Studio backend. Mirrors the inline exponential-backoff shape that already lived in
image_generator.generate_background_image() and html_carousel.translate_script(),
so retry behavior is consistent across the codebase.

Usage:
    from retry_utils import retry

    result = retry(
        lambda: client.do_thing(),
        attempts=3,
        base_delay=3.0,
        exceptions=(RuntimeError,),
        on_retry=lambda attempt, exc: print(f"retry {attempt}: {exc}"),
    )
"""
from __future__ import annotations

import time
from typing import Callable, TypeVar

T = TypeVar("T")


def retry(
    fn: Callable[[], T],
    *,
    attempts: int = 3,
    base_delay: float = 2.0,
    backoff: float = 1.0,
    exceptions: tuple[type[BaseException], ...] = (Exception,),
    on_retry: Callable[[int, BaseException], None] | None = None,
) -> T:
    """Call ``fn`` up to ``attempts`` times, retrying on ``exceptions``.

    Args:
        fn:         Zero-arg callable to invoke.
        attempts:   Total number of tries (>= 1). ``attempts=3`` means 1 try + 2 retries.
        base_delay: Seconds to wait before the first retry.
        backoff:    Multiplier applied to the delay each subsequent retry.
                    ``backoff=1.0`` keeps a constant delay; ``2.0`` doubles it.
        exceptions: Exception types that trigger a retry. Anything else propagates.
        on_retry:   Optional callback ``(attempt_number, exception)`` invoked before
                    each wait, e.g. for logging.

    Returns:
        Whatever ``fn`` returns on the first successful call.

    Raises:
        The last exception if all attempts fail.
    """
    if attempts < 1:
        raise ValueError("attempts must be >= 1")

    last_exc: BaseException | None = None
    delay = base_delay

    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except exceptions as exc:
            last_exc = exc
            if attempt >= attempts:
                break
            if on_retry is not None:
                on_retry(attempt, exc)
            time.sleep(delay)
            delay *= backoff

    assert last_exc is not None  # only reachable after a failed attempt
    raise last_exc
