from __future__ import annotations

import time
from threading import Lock
from uuid import uuid4

from django.conf import settings


class PresenceBackend:
    ttl_seconds = 45

    def __init__(self):
        self._redis = None
        self._lock = Lock()
        self._local: dict[str, float] = {}
        redis_url = getattr(settings, "REDIS_URL", None)
        if redis_url:
            try:
                import redis

                self._redis = redis.from_url(redis_url, decode_responses=True)
                self._redis.ping()
            except Exception:
                self._redis = None

    def new_connection_id(self) -> str:
        return uuid4().hex

    def _key(self, match_id, color, connection_id) -> str:
        return f"chessclub:presence:match:{match_id}:{color}:{connection_id}"

    def connect(self, match_id, color, connection_id) -> bool:
        key = self._key(match_id, color, connection_id)
        if self._redis:
            self._redis.setex(key, self.ttl_seconds, "1")
            return self.is_connected(match_id, color)
        with self._lock:
            self._local[key] = time.time() + self.ttl_seconds
            self._prune_locked()
            return self._has_color_locked(match_id, color)

    def heartbeat(self, match_id, color, connection_id) -> None:
        key = self._key(match_id, color, connection_id)
        if self._redis:
            self._redis.setex(key, self.ttl_seconds, "1")
            return
        with self._lock:
            self._local[key] = time.time() + self.ttl_seconds
            self._prune_locked()

    def disconnect(self, match_id, color, connection_id) -> bool:
        key = self._key(match_id, color, connection_id)
        if self._redis:
            self._redis.delete(key)
            return self.is_connected(match_id, color)
        with self._lock:
            self._local.pop(key, None)
            self._prune_locked()
            return self._has_color_locked(match_id, color)

    def is_connected(self, match_id, color) -> bool:
        if self._redis:
            return next(self._redis.scan_iter(self._key(match_id, color, "*"), count=10), None) is not None
        with self._lock:
            self._prune_locked()
            return self._has_color_locked(match_id, color)

    def _prune_locked(self):
        now = time.time()
        expired = [key for key, expires_at in self._local.items() if expires_at <= now]
        for key in expired:
            self._local.pop(key, None)

    def _has_color_locked(self, match_id, color) -> bool:
        prefix = self._key(match_id, color, "")
        return any(key.startswith(prefix) for key in self._local)


presence_backend = PresenceBackend()
