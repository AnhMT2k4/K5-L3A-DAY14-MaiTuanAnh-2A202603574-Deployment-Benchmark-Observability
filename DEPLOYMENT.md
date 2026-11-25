# Deployment Information

## Public URL
https://production-agent-k5-day14.up.railway.app

## Platform
Railway (hoặc Render Blueprint)

## Test Commands

### Health Check
```bash
curl -sS -o /dev/null -w '%{http_code}\n' https://production-agent-k5-day14.up.railway.app/health
# Expected: 200
```

### Readiness Check
```bash
curl -sS -o /dev/null -w '%{http_code}\n' https://production-agent-k5-day14.up.railway.app/ready
# Expected: 200
```

### API Test (không có API Key — mong đợi 401)
```bash
curl -sS -o /dev/null -w '%{http_code}\n' -X POST https://production-agent-k5-day14.up.railway.app/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "Hello"}'
# Expected: 401
```

### API Test (có API Key hợp lệ — mong đợi 200)
```bash
curl -sS -o /dev/null -w '%{http_code}\n' -X POST https://production-agent-k5-day14.up.railway.app/ask \
  -H "X-API-Key: $AGENT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"question": "Hello"}'
# Expected: 200
```

## Environment Variables Set
- `PORT`: 8000
- `ENVIRONMENT`: production
- `AGENT_API_KEY`: [Configured securely via Platform Secrets]
- `REDIS_URL`: [Configured securely via Platform Managed Redis Connection String]
- `RATE_LIMIT_PER_MINUTE`: 10
- `DAILY_BUDGET_USD`: 10.0
- `MONTHLY_BUDGET_USD`: 100.0

## Screenshots
- [Deployment dashboard](screenshots/dashboard.png)
- [Service running](screenshots/running.png)
- [Test results](screenshots/test.png)
