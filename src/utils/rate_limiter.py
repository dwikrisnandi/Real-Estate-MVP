"""
Rate Limiter
============
Provides configurable rate limiting with human-like jitter and
automatic back-off on 429 responses.
"""

import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta


@dataclass
class RateLimiterConfig:
    """Rate limiter configuration."""
    min_delay: float = 1.5
    max_delay: float = 4.0
    jitter: bool = True
    backoff_multiplier: float = 2.0
    max_backoff: float = 60.0
    # For hourly / daily caps
    max_per_hour: int = 0       # 0 = no limit
    max_per_day: int = 0        # 0 = no limit
    batch_size: int = 0         # 0 = no batching
    batch_pause_seconds: float = 0.0


class RateLimiter:
    """
    Enforces rate limits with human-like timing behavior.

    Features:
    - Random delay between min and max with optional jitter
    - Exponential back-off on repeated rate-limit hits
    - Hourly and daily caps
    - Batch pausing (e.g., pause 10 min every 5 messages)
    """

    def __init__(self, config: RateLimiterConfig | None = None):
        self._config = config or RateLimiterConfig()
        self._current_backoff: float = 0
        self._action_count: int = 0
        self._hourly_timestamps: list[datetime] = []
        self._daily_timestamps: list[datetime] = []
        self._last_action: float = 0

    def wait(self) -> float:
        """
        Block until it's safe to perform the next action.

        Returns:
            The actual delay in seconds that was applied.
        """
        # ── Check daily cap ──
        if self._config.max_per_day > 0:
            self._prune_timestamps(self._daily_timestamps, hours=24)
            if len(self._daily_timestamps) >= self._config.max_per_day:
                raise RateLimitExceeded(
                    f"Daily limit reached ({self._config.max_per_day}). "
                    f"Resuming after midnight."
                )

        # ── Check hourly cap ──
        if self._config.max_per_hour > 0:
            self._prune_timestamps(self._hourly_timestamps, hours=1)
            if len(self._hourly_timestamps) >= self._config.max_per_hour:
                oldest = self._hourly_timestamps[0]
                wait_until = oldest + timedelta(hours=1)
                sleep_secs = (wait_until - datetime.now()).total_seconds()
                if sleep_secs > 0:
                    time.sleep(sleep_secs)
                self._prune_timestamps(self._hourly_timestamps, hours=1)

        # ── Calculate delay ──
        base_delay = random.uniform(
            self._config.min_delay,
            self._config.max_delay,
        )

        if self._config.jitter:
            # Add ±20% human-like jitter
            jitter_range = base_delay * 0.2
            base_delay += random.uniform(-jitter_range, jitter_range)

        # Apply any active back-off
        total_delay = base_delay + self._current_backoff

        # Ensure minimum time since last action
        elapsed = time.time() - self._last_action
        if elapsed < total_delay:
            actual_sleep = total_delay - elapsed
            time.sleep(actual_sleep)
        else:
            actual_sleep = 0

        # Record the action
        now = datetime.now()
        self._last_action = time.time()
        self._action_count += 1
        self._hourly_timestamps.append(now)
        self._daily_timestamps.append(now)

        # Reset back-off after successful action
        self._current_backoff = 0

        # ── Batch pausing ──
        if (
            self._config.batch_size > 0
            and self._action_count % self._config.batch_size == 0
            and self._config.batch_pause_seconds > 0
        ):
            time.sleep(self._config.batch_pause_seconds)
            actual_sleep += self._config.batch_pause_seconds

        return actual_sleep

    def report_rate_limited(self) -> float:
        """
        Call this when a 429 / rate-limit response is received.
        Increases the back-off exponentially.

        Returns:
            The new back-off duration in seconds.
        """
        if self._current_backoff == 0:
            self._current_backoff = self._config.min_delay
        else:
            self._current_backoff = min(
                self._current_backoff * self._config.backoff_multiplier,
                self._config.max_backoff,
            )
        return self._current_backoff

    def reset(self) -> None:
        """Reset all counters and back-off state."""
        self._current_backoff = 0
        self._action_count = 0
        self._hourly_timestamps.clear()
        self._daily_timestamps.clear()

    @property
    def actions_performed(self) -> int:
        return self._action_count

    @staticmethod
    def _prune_timestamps(timestamps: list[datetime], hours: int) -> None:
        """Remove timestamps older than `hours` hours."""
        cutoff = datetime.now() - timedelta(hours=hours)
        while timestamps and timestamps[0] < cutoff:
            timestamps.pop(0)


class RateLimitExceeded(Exception):
    """Raised when a rate limit cap (hourly/daily) has been reached."""
    pass
