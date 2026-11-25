import redis
from app.config import settings

_redis_clients = {}


def get_redis():
    url = settings.redis_url
    if not url:
        return None
    if url not in _redis_clients:
        try:
            _redis_clients[url] = redis.from_url(
                url, decode_responses=True, socket_connect_timeout=2, socket_timeout=2
            )
        except Exception:
            return None
    return _redis_clients[url]


class RedisProxy:
    def __getattr__(self, name):
        client = get_redis()
        if client is None:
            raise ConnectionError("Redis not available")
        return getattr(client, name)


r = RedisProxy()


def redis_healthy() -> bool:
    try:
        client = get_redis()
        if client is None:
            return False
        return bool(client.ping())
    except Exception:
        return False
