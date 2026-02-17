"""Redis-backed cache utilities with graceful fallback behavior."""
import json
import logging
from typing import Any, Optional

from redis import Redis
from redis.exceptions import RedisError

from app.config import (
    CACHE_ENABLED,
    CACHE_KEY_PREFIX,
    REDIS_DB,
    REDIS_HOST,
    REDIS_PASSWORD,
    REDIS_PORT,
    REDIS_SOCKET_TIMEOUT_SECONDS,
    REDIS_SSL,
)

logger = logging.getLogger(__name__)

_redis_client: Optional[Redis] = None
_redis_connected = False


def _namespaced_key(key: str) -> str:
    if key.startswith(f"{CACHE_KEY_PREFIX}:"):
        return key
    return f"{CACHE_KEY_PREFIX}:{key}"


def _parse_json(raw_value: str) -> Any:
    try:
        return json.loads(raw_value)
    except (TypeError, ValueError):
        return None


def init_cache() -> None:
    """Initialize Redis client and verify connectivity."""
    global _redis_client, _redis_connected

    if not CACHE_ENABLED:
        logger.info("Cache disabled via CACHE_ENABLED=false")
        _redis_client = None
        _redis_connected = False
        return

    try:
        _redis_client = Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            db=REDIS_DB,
            password=REDIS_PASSWORD,
            ssl=REDIS_SSL,
            socket_timeout=REDIS_SOCKET_TIMEOUT_SECONDS,
            decode_responses=True,
        )
        _redis_client.ping()
        _redis_connected = True
        logger.info("Redis cache connected at %s:%s db=%s", REDIS_HOST, REDIS_PORT, REDIS_DB)
    except RedisError as exc:
        logger.warning("Redis cache unavailable, continuing without cache: %s", exc)
        _redis_client = None
        _redis_connected = False


def close_cache() -> None:
    """Close Redis connection on shutdown."""
    global _redis_client, _redis_connected
    if _redis_client is None:
        return

    try:
        _redis_client.close()
    except RedisError as exc:
        logger.warning("Error closing Redis connection: %s", exc)
    finally:
        _redis_client = None
        _redis_connected = False


def is_cache_available() -> bool:
    return CACHE_ENABLED and _redis_connected and _redis_client is not None


def get_cache_status() -> dict[str, Any]:
    return {
        "enabled": CACHE_ENABLED,
        "connected": is_cache_available(),
        "backend": "redis",
        "host": REDIS_HOST if CACHE_ENABLED else None,
        "port": REDIS_PORT if CACHE_ENABLED else None,
        "db": REDIS_DB if CACHE_ENABLED else None,
    }


def make_cache_key(*parts: Any) -> str:
    """Create deterministic cache key from key parts."""
    normalized_parts = [
        str(part).strip().replace(" ", "_")
        for part in parts
        if part is not None and str(part).strip()
    ]
    return _namespaced_key(":".join(normalized_parts))


def get_cached_json(key: str) -> Any:
    """Fetch and deserialize JSON payload from Redis."""
    if not is_cache_available():
        return None

    try:
        raw_value = _redis_client.get(_namespaced_key(key))
        if raw_value is None:
            return None
        return _parse_json(raw_value)
    except RedisError as exc:
        logger.debug("Cache read error for key=%s: %s", key, exc)
        return None


def set_cached_json(key: str, value: Any, ttl_seconds: int) -> bool:
    """Serialize payload to JSON and store in Redis with TTL."""
    if not is_cache_available():
        return False

    try:
        payload = json.dumps(value, default=str, ensure_ascii=True, separators=(",", ":"))
        _redis_client.setex(_namespaced_key(key), ttl_seconds, payload)
        return True
    except (RedisError, TypeError, ValueError) as exc:
        logger.debug("Cache write error for key=%s: %s", key, exc)
        return False


def invalidate_cache_key(key: str) -> None:
    """Delete a specific cache key."""
    if not is_cache_available():
        return

    try:
        _redis_client.delete(_namespaced_key(key))
    except RedisError as exc:
        logger.debug("Cache invalidate key error for key=%s: %s", key, exc)


def invalidate_cache_prefix(prefix: str) -> int:
    """Delete all cache keys matching a prefix, returns number of deleted keys."""
    if not is_cache_available():
        return 0

    namespaced_prefix = _namespaced_key(prefix)
    pattern = f"{namespaced_prefix}*"
    deleted = 0

    try:
        for cache_key in _redis_client.scan_iter(match=pattern, count=100):
            deleted += int(_redis_client.delete(cache_key))
    except RedisError as exc:
        logger.debug("Cache invalidate prefix error for prefix=%s: %s", prefix, exc)
        return 0

    return deleted
