import json
import logging
import sys
import time
from datetime import datetime, timezone
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException, Request, Response, Query, Body
from pydantic import BaseModel, Field

from app.config import settings
from app.auth import verify_api_key
from app.rate_limiter import check_rate_limit
from app.cost_guard import check_budget, record_cost
from app.redis_client import redis_healthy
from utils.mock_llm import ask as llm_ask


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_obj = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "lvl": record.levelname,
            "msg": record.getMessage(),
            "logger": record.name,
        }
        return json.dumps(log_obj)


logger = logging.getLogger("app")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(JsonFormatter())
logger.handlers = [handler]
logger.propagate = False


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Log startup
    log_entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "lvl": "INFO",
        "event": "startup",
        "msg": "Application startup complete",
    }
    print(json.dumps(log_entry), flush=True)
    yield
    # Log shutdown (SIGTERM handled)
    log_entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "lvl": "INFO",
        "event": "shutdown",
        "msg": "Application shutdown complete (SIGTERM handled)",
    }
    print(json.dumps(log_entry), flush=True)


app = FastAPI(title="Production AI Agent", lifespan=lifespan)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response: Response = await call_next(request)
    duration_ms = (time.time() - start_time) * 1000
    log_entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "lvl": "INFO",
        "event": "request",
        "method": request.method,
        "path": request.url.path,
        "status": response.status_code,
        "ms": round(duration_ms, 2),
    }
    print(json.dumps(log_entry), flush=True)
    return response


class AskRequest(BaseModel):
    question: Optional[str] = None
    user_id: Optional[str] = None


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/ready")
def ready():
    if not redis_healthy():
        raise HTTPException(status_code=503, detail="Redis connection unavailable")
    return {"status": "ready", "redis": "connected"}


@app.post("/ask")
def ask(
    body: Optional[AskRequest] = Body(None),
    question: Optional[str] = Query(None),
    api_key: str = Depends(verify_api_key),
):
    q = ""
    if body and body.question:
        q = body.question
    elif question:
        q = question

    if not q:
        raise HTTPException(status_code=400, detail="Missing question")

    check_rate_limit(api_key)
    check_budget()

    answer = llm_ask(q)

    input_tokens = max(1, len(q.split()))
    output_tokens = max(1, len(answer.split()))
    record_cost(input_tokens, output_tokens)

    return {"question": q, "answer": answer}
