"""Circuit breaker pattern implementation for fault tolerance"""

import time
from enum import Enum
from typing import Callable, Optional, TypeVar, Any

from .exceptions import ExchangeError
from .logging import get_logger

logger = get_logger()

T = TypeVar('T')


class CircuitState(Enum):
    """Circuit breaker states"""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if service recovered


class CircuitBreaker:
    """Circuit breaker to prevent cascading failures"""

    def __init__(
        self,
        failure_threshold: int = 5,
        timeout: int = 60,
        name: str = "circuit_breaker"
    ):
        self.failure_threshold = failure_threshold
        self.timeout = timeout  # seconds
        self.name = name
        self.failure_count = 0
        self.last_failure_time = 0.0
        self.state = CircuitState.CLOSED

    def call(self, func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """Execute function with circuit breaker protection"""
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time >= self.timeout:
                logger.info(f"Circuit breaker {self.name}: transitioning to HALF_OPEN")
                self.state = CircuitState.HALF_OPEN
            else:
                raise ExchangeError(f"Circuit breaker {self.name} is OPEN")

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise

    async def call_async(self, func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """Execute async function with circuit breaker protection"""
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time >= self.timeout:
                logger.info(f"Circuit breaker {self.name}: transitioning to HALF_OPEN")
                self.state = CircuitState.HALF_OPEN
            else:
                raise ExchangeError(f"Circuit breaker {self.name} is OPEN")

        try:
            result = await func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise

    def _on_success(self) -> None:
        """Handle successful call"""
        if self.state == CircuitState.HALF_OPEN:
            logger.info(f"Circuit breaker {self.name}: transitioning to CLOSED")
            self.state = CircuitState.CLOSED
        self.failure_count = 0

    def _on_failure(self) -> None:
        """Handle failed call"""
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.failure_count >= self.failure_threshold:
            if self.state != CircuitState.OPEN:
                logger.warning(
                    f"Circuit breaker {self.name}: transitioning to OPEN "
                    f"(failures: {self.failure_count})"
                )
                self.state = CircuitState.OPEN

    def reset(self) -> None:
        """Reset circuit breaker to closed state"""
        self.failure_count = 0
        self.state = CircuitState.CLOSED
        logger.info(f"Circuit breaker {self.name}: reset to CLOSED")

    def get_state(self) -> str:
        """Get current circuit breaker state"""
        return self.state.value
