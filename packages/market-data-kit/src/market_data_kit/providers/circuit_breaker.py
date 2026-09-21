"""Circuit breaker for provider resilience."""
from __future__ import annotations

import time
import logging

__all__ = ["CircuitBreaker", "CircuitOpenError"]

logger = logging.getLogger(__name__)


class CircuitOpenError(Exception):
    """Raised when a call is rejected because the circuit is open."""


class CircuitBreaker:
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

    def __init__(self, name: str, failure_threshold: int = 3,
                 cooldown_seconds: float = 300, half_open_trials: int = 1):
        self.name = name
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.half_open_trials = half_open_trials
        self._state = self.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: float = 0

    @property
    def state(self) -> str:
        if self._state == self.OPEN:
            if time.monotonic() - self._last_failure_time >= self.cooldown_seconds:
                self._state = self.HALF_OPEN
                self._success_count = 0
        return self._state

    @property
    def retry_after(self) -> float:
        """Seconds until circuit breaker may allow requests again. 0 if closed/half-open."""
        if self._state != self.OPEN:
            return 0.0
        remaining = self.cooldown_seconds - (time.monotonic() - self._last_failure_time)
        return max(0.0, remaining)

    def allow_request(self) -> bool:
        s = self.state
        if s == self.CLOSED:
            return True
        if s == self.HALF_OPEN:
            return True
        return False  # OPEN

    def record_success(self) -> None:
        if self._state == self.HALF_OPEN:
            self._success_count += 1
            if self._success_count >= self.half_open_trials:
                self._state = self.CLOSED
                self._failure_count = 0
                self._success_count = 0
                logger.info("CircuitBreaker[%s]: HALF_OPEN → CLOSED", self.name)
        else:
            self._failure_count = 0

    def record_failure(self) -> None:
        self._failure_count += 1
        self._last_failure_time = time.monotonic()
        if self._state == self.HALF_OPEN:
            self._state = self.OPEN
            logger.warning("CircuitBreaker[%s]: HALF_OPEN → OPEN", self.name)
        elif self._failure_count >= self.failure_threshold:
            self._state = self.OPEN
            logger.warning("CircuitBreaker[%s]: CLOSED → OPEN (failures=%d)",
                           self.name, self._failure_count)

    def reset(self) -> None:
        self._state = self.CLOSED
        self._failure_count = 0
        self._success_count = 0
