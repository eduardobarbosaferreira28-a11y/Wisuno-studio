"""Unit tests for retry_utils.retry."""
import pytest

from retry_utils import retry


def test_returns_first_success_without_retrying():
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        return "ok"

    assert retry(fn, attempts=3, base_delay=0) == "ok"
    assert calls["n"] == 1


def test_retries_then_succeeds():
    calls = {"n": 0}
    retried: list[int] = []

    def fn():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ValueError("boom")
        return "ok"

    result = retry(
        fn,
        attempts=3,
        base_delay=0,
        exceptions=(ValueError,),
        on_retry=lambda attempt, exc: retried.append(attempt),
    )
    assert result == "ok"
    assert calls["n"] == 3
    assert retried == [1, 2]  # on_retry fires before each wait, not after the last try


def test_raises_last_exception_after_exhaustion():
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        raise KeyError(f"fail-{calls['n']}")

    with pytest.raises(KeyError):
        retry(fn, attempts=2, base_delay=0, exceptions=(KeyError,))
    assert calls["n"] == 2


def test_non_matching_exception_propagates_immediately():
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        raise TypeError("wrong type")

    with pytest.raises(TypeError):
        retry(fn, attempts=5, base_delay=0, exceptions=(ValueError,))
    assert calls["n"] == 1  # not retried


def test_invalid_attempts_rejected():
    with pytest.raises(ValueError):
        retry(lambda: None, attempts=0)
