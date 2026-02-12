"""Retry decorators with exponential backoff using tenacity"""

from functools import wraps
from typing import Callable, Type, Tuple, TypeVar

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)

from .logging import get_logger
from .exceptions import ConnectionError, RateLimitError, APIError

logger = get_logger()

T = TypeVar('T')


def retry_on_connection_error(
    max_attempts: int = 3,
    min_wait: int = 1,
    max_wait: int = 10,
) -> Callable:
    """Retry decorator for connection errors with exponential backoff"""
    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=1, min=min_wait, max=max_wait),
        retry=retry_if_exception_type((ConnectionError, TimeoutError)),
        before_sleep=before_sleep_log(logger, "warning"),
        reraise=True,
    )


def retry_on_rate_limit(
    max_attempts: int = 5,
    min_wait: int = 2,
    max_wait: int = 30,
) -> Callable:
    """Retry decorator for rate limit errors with longer backoff"""
    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=2, min=min_wait, max=max_wait),
        retry=retry_if_exception_type(RateLimitError),
        before_sleep=before_sleep_log(logger, "warning"),
        reraise=True,
    )


def retry_on_api_error(
    max_attempts: int = 3,
    min_wait: int = 1,
    max_wait: int = 10,
    retry_status_codes: Tuple[int, ...] = (500, 502, 503, 504),
) -> Callable:
    """Retry decorator for API errors with specific status codes"""
    def should_retry(exception: Exception) -> bool:
        if isinstance(exception, APIError):
            return exception.status_code in retry_status_codes
        return False

    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=1, min=min_wait, max=max_wait),
        retry=retry_if_exception(should_retry),
        before_sleep=before_sleep_log(logger, "warning"),
        reraise=True,
    )


def retry_if_exception(predicate: Callable[[Exception], bool]) -> Callable:
    """Custom retry predicate"""
    def _retry_if_exception(exception: Exception) -> bool:
        return predicate(exception)
    return _retry_if_exception
