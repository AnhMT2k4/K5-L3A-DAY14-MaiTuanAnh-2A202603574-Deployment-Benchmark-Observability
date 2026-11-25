from fastapi import HTTPException
from app.config import settings
from app.redis_client import get_redis

# Giá USD / 1K tokens (tham khảo gpt-4o-mini)
PRICE_INPUT_PER_1K = 0.00015
PRICE_OUTPUT_PER_1K = 0.0006

COST_KEY = "cost_guard:total_cost"


def check_budget() -> None:
    """Gọi TRƯỚC khi gọi LLM. Hết budget → raise HTTPException(status_code=402)."""
    client = get_redis()
    if client is None:
        return
    current_cost_str = client.get(COST_KEY)
    current_cost = float(current_cost_str) if current_cost_str else 0.0
    budget = min(settings.daily_budget_usd, settings.monthly_budget_usd)
    if current_cost >= budget:
        raise HTTPException(
            status_code=402,
            detail=f"Budget exceeded: current cost ${current_cost:.6f} >= budget ${budget:.6f}",
        )


def record_cost(input_tokens: int, output_tokens: int) -> float:
    """Gọi SAU khi gọi LLM. Cộng chi phí của request vào tổng, trả về chi phí request."""
    client = get_redis()
    cost = (input_tokens / 1000.0) * PRICE_INPUT_PER_1K + (output_tokens / 1000.0) * PRICE_OUTPUT_PER_1K
    if client is not None:
        client.incrbyfloat(COST_KEY, cost)
    return cost
