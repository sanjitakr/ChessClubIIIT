from __future__ import annotations

import json
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

import logging

logger = logging.getLogger(__name__)

REDIS_QUEUE_KEY = "chessclub:matchmaking:queue"
REDIS_MATCH_PREFIX = "chessclub:matchmaking:matched:"


@dataclass
class QueueEntry:
    user_id: int
    username: str
    rating: int
    queued_at: float = field(default_factory=time.time)

    def wait_seconds(self) -> float:
        return time.time() - self.queued_at

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "username": self.username,
            "rating": self.rating,
            "queued_at": self.queued_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> QueueEntry:
        return cls(
            user_id=data["user_id"],
            username=data["username"],
            rating=data["rating"],
            queued_at=data.get("queued_at", time.time()),
        )


@dataclass
class PairingResult:
    player1: QueueEntry
    player2: QueueEntry
    rating_diff: int = 0

    def __post_init__(self):
        self.rating_diff = abs(self.player1.rating - self.player2.rating)


class IPairingStrategy(ABC):
    @abstractmethod
    def find_pair(self, entries: list[QueueEntry]) -> Optional[PairingResult]:
        raise NotImplementedError


class RatingBasedPairingStrategy(IPairingStrategy):
    """FIDE-inspired rating pairing with expanding window over wait time."""

    def __init__(self, ideal_diff: int = 200, max_wait_seconds: float = 60.0):
        self.ideal_diff = ideal_diff
        self.max_wait_seconds = max_wait_seconds

    def find_pair(self, entries: list[QueueEntry]) -> Optional[PairingResult]:
        if len(entries) < 2:
            return None
        best: Optional[PairingResult] = None
        best_diff = float("inf")
        for i in range(len(entries)):
            for j in range(i + 1, len(entries)):
                a, b = entries[i], entries[j]
                diff = abs(a.rating - b.rating)
                max_diff = self._allowed_diff(a, b)
                if diff <= max_diff and diff < best_diff:
                    best_diff = diff
                    best = PairingResult(player1=a, player2=b)
        return best

    def _allowed_diff(self, a: QueueEntry, b: QueueEntry) -> float:
        max_wait = max(a.wait_seconds(), b.wait_seconds())
        if max_wait >= self.max_wait_seconds:
            return float("inf")
        ratio = max_wait / self.max_wait_seconds
        return self.ideal_diff + (1000 * ratio)


class MatchmakingQueue:
    """In-memory fallback queue."""

    def __init__(self):
        self._lock = threading.Lock()
        self._entries: dict[int, QueueEntry] = {}

    def enqueue(self, entry: QueueEntry) -> None:
        with self._lock:
            self._entries[entry.user_id] = entry

    def dequeue(self, user_id: int) -> Optional[QueueEntry]:
        with self._lock:
            return self._entries.pop(user_id, None)

    def contains(self, user_id: int) -> bool:
        with self._lock:
            return user_id in self._entries

    def snapshot(self) -> list[QueueEntry]:
        with self._lock:
            return sorted(self._entries.values(), key=lambda e: e.queued_at)

    def remove_pair(self, result: PairingResult) -> None:
        with self._lock:
            self._entries.pop(result.player1.user_id, None)
            self._entries.pop(result.player2.user_id, None)

    def size(self) -> int:
        with self._lock:
            return len(self._entries)


class RedisMatchmakingQueue(MatchmakingQueue):
    """Redis-backed queue for multi-worker production deployments."""

    def __init__(self, redis_url: str):
        super().__init__()
        import redis
        self._redis = redis.from_url(redis_url, decode_responses=True)
        self._use_redis = True

    def _load_all(self) -> dict[int, QueueEntry]:
        raw = self._redis.hgetall(REDIS_QUEUE_KEY)
        return {int(k): QueueEntry.from_dict(json.loads(v)) for k, v in raw.items()}

    def enqueue(self, entry: QueueEntry) -> None:
        self._redis.hset(REDIS_QUEUE_KEY, str(entry.user_id), json.dumps(entry.to_dict()))

    def dequeue(self, user_id: int) -> Optional[QueueEntry]:
        raw = self._redis.hget(REDIS_QUEUE_KEY, str(user_id))
        if raw:
            self._redis.hdel(REDIS_QUEUE_KEY, str(user_id))
            return QueueEntry.from_dict(json.loads(raw))
        return None

    def contains(self, user_id: int) -> bool:
        return self._redis.hexists(REDIS_QUEUE_KEY, str(user_id))

    def snapshot(self) -> list[QueueEntry]:
        return sorted(self._load_all().values(), key=lambda e: e.queued_at)

    def remove_pair(self, result: PairingResult) -> None:
        pipe = self._redis.pipeline()
        pipe.hdel(REDIS_QUEUE_KEY, str(result.player1.user_id))
        pipe.hdel(REDIS_QUEUE_KEY, str(result.player2.user_id))
        pipe.execute()

    def size(self) -> int:
        return self._redis.hlen(REDIS_QUEUE_KEY)

    def store_match_notification(self, user_id: int, data: dict, ttl: int = 120) -> None:
        self._redis.setex(f"{REDIS_MATCH_PREFIX}{user_id}", ttl, json.dumps(data))

    def pop_match_notification(self, user_id: int) -> Optional[dict]:
        key = f"{REDIS_MATCH_PREFIX}{user_id}"
        raw = self._redis.get(key)
        if raw:
            self._redis.delete(key)
            return json.loads(raw)
        return None


def _create_queue():
    try:
        from django.conf import settings
        url = getattr(settings, "REDIS_URL", None)
        if url:
            q = RedisMatchmakingQueue(url)
            q._redis.ping()
            logger.info("Matchmaking queue using Redis backend")
            return q
    except Exception as exc:
        logger.warning("Redis queue unavailable, using in-memory: %s", exc)
    return MatchmakingQueue()


class PairingService:
    def __init__(self, queue: MatchmakingQueue, strategy: IPairingStrategy):
        self._queue = queue
        self._strategy = strategy

    def join_queue(self, user_id: int, username: str, rating: int) -> bool:
        if self._queue.contains(user_id):
            return False
        self._queue.enqueue(QueueEntry(user_id=user_id, username=username, rating=rating))
        return True

    def leave_queue(self, user_id: int) -> bool:
        return self._queue.dequeue(user_id) is not None

    def is_in_queue(self, user_id: int) -> bool:
        return self._queue.contains(user_id)

    def try_pair(self) -> Optional[PairingResult]:
        snapshot = self._queue.snapshot()
        result = self._strategy.find_pair(snapshot)
        if result:
            self._queue.remove_pair(result)
        return result

    def queue_snapshot(self) -> list[QueueEntry]:
        return self._queue.snapshot()

    def queue_size(self) -> int:
        return self._queue.size()

    def notify_match(self, user_id: int, data: dict) -> None:
        if isinstance(self._queue, RedisMatchmakingQueue):
            self._queue.store_match_notification(user_id, data)

    def get_match_notification(self, user_id: int) -> Optional[dict]:
        if isinstance(self._queue, RedisMatchmakingQueue):
            return self._queue.pop_match_notification(user_id)
        return None


_global_queue = _create_queue()

rating_pairing_service = PairingService(
    queue=_global_queue,
    strategy=RatingBasedPairingStrategy(ideal_diff=200, max_wait_seconds=60),
)
