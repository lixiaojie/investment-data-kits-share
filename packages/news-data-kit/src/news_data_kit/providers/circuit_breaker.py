"""Circuit breaker for news providers.

Three states: CLOSED (normal) → OPEN (failures exceeded) → HALF_OPEN (probe).
"""

from __future__ import annotations

import logging
import time

logger = logging.getLogger(__name__)

CLOSED = "closed"
OPEN = "open"
HALF_OPEN = "half_open"


class CircuitBreaker:
    __slots__ = (
        "name", "failure_threshold", "cooldown_seconds", "half_open_trials",
        "_state", "_failure_count", "_last_failure_time", "_half_open_successes",
    )

    def __init__(
        self,
        name: str,
        failure_threshold: int = 3,
        cooldown_seconds: float = 300,
        half_open_trials: int = 1,
    ) -> None:
        self.name = name
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.half_open_trials = half_open_trials
        self._state = CLOSED
        self._failure_count = 0
        self._last_failure_time = 0.0
        self._half_open_successes = 0

    @property
    def state(self) -> str:
        self._maybe_transition()
        return self._state

    def allow_request(self) -> bool:
        self._maybe_transition()
        return self._state != OPEN

    def record_success(self) -> None:
        self._maybe_transition()
        if self._state == HALF_OPEN:
            self._half_open_successes += 1
            if self._half_open_successes >= self.half_open_trials:
                self._transition(CLOSED)
        elif self._state == CLOSED:
            self._failure_count = 0

    def record_failure(self) -> None:
        self._failure_count += 1
        self._last_failure_time = time.monotonic()
        if self._state == HALF_OPEN:
            self._transition(OPEN)
        elif self._failure_count >= self.failure_threshold:
            self._transition(OPEN)

    def reset(self) -> None:
        self._transition(CLOSED)

    def _maybe_transition(self) -> None:
        if self._state == OPEN:
            if time.monotonic() - self._last_failure_time >= self.cooldown_seconds:
                self._transition(HALF_OPEN)

    def _transition(self, new: str) -> None:
        old = self._state
        self._state = new
        if new == CLOSED:
            self._failure_count = 0
            self._half_open_successes = 0
        elif new == HALF_OPEN:
            self._half_open_successes = 0
        if old != new:
            logger.info("CB[%s]: %s → %s", self.name, old, new)
