import secrets
from datetime import datetime, timedelta, timezone
from typing import Dict
from fastapi import HTTPException, status

from app.core.config import settings


# ── Simple token-bucket rate limiter per device ────────────────────────────
class RateLimiter:
    """Max N commands per second per device (doc §6 security)."""

    def __init__(self, max_per_second: int = settings.MAX_COMMANDS_PER_SECOND):
        self._max = max_per_second
        self._buckets: Dict[str, list] = {}  # device_id → list[datetime]

    def check(self, device_id: str) -> None:
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(seconds=1)
        timestamps = [t for t in self._buckets.get(device_id, []) if t > window_start]
        if len(timestamps) >= self._max:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Command rate limit exceeded",
            )
        timestamps.append(now)
        self._buckets[device_id] = timestamps

        # Periodic cleanup if map grows too large to avoid memory exhaustion
        if len(self._buckets) > 500:
            stale_keys = [k for k, v in self._buckets.items() if not v or v[-1] <= window_start]
            for k in stale_keys:
                self._buckets.pop(k, None)


rate_limiter = RateLimiter()


def verify_pairing_code(code: str) -> bool:
    """Validate the pairing code sent by a connecting device with constant-time comparison."""
    if not code:
        return False
    return secrets.compare_digest(code, settings.PAIRING_SECRET)
