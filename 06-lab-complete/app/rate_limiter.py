import time
from fastapi import HTTPException
from app.config import settings
from app.redis_client import get_redis


def check_rate_limit(key: str) -> None:
    client = get_redis()
    if client is None:
        return

    limit = settings.rate_limit_per_minute
    now = time.time()
    window = 60
    redis_key = f"rate_limit:{key}"

    pipe = client.pipeline()
    pipe.zremrangebyscore(redis_key, "-inf", now - window)
    pipe.zcard(redis_key)
    results = pipe.execute()
    current_count = results[1]

    if current_count >= limit:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded: {limit} requests per minute",
            headers={"Retry-After": "60"},
        )

    pipe = client.pipeline()
    pipe.zadd(redis_key, {f"{now}-{current_count}": now})
    pipe.expire(redis_key, window)
    pipe.execute()
