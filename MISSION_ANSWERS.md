# Day 14 Lab — Mission Answers

> **Họ và tên:** Mai Tuấn Anh  
> **MSSV:** 2A202603574  
> **Lớp:** K5-L3A  
> **Repository:** `K5-L3A-DAY14-MaiTuanAnh-2A202603574-Deployment-Benchmark-Observability`  

---

## Part 1: Localhost vs Production

### Exercise 1.1: Anti-patterns found in `01-localhost-vs-production/develop/app.py`
1. **Hardcoded Secrets & Credentials:** Biến `OPENAI_API_KEY = "sk-hardcoded-fake-key-never-do-this"` và `DATABASE_URL = "postgresql://admin:password123@localhost:5432/mydb"` được viết cứng trực tiếp trong source code. Khi commit lên Git, secret sẽ bị lộ ngay lập tức.
2. **Thiếu quản lý cấu hình (Config Management):** Các biến cấu hình như `DEBUG = True`, `MAX_TOKENS = 500` bị hardcode, không đọc qua biến môi trường theo nguyên lý 12-Factor App.
3. **Insecure Logging:** Dùng hàm `print()` tiêu chuẩn thay vì logger chuyên dụng, và đặc biệt là in cả secret ra log console (`print(f"[DEBUG] Using key: {OPENAI_API_KEY}")`), gây rò rỉ thông tin nhạy cảm vào log file.
4. **Không có Health Check Endpoints:** Thiếu cả endpoint `/health` (liveness probe) lẫn `/ready` (readiness probe). Khi ứng dụng bị treo hoặc database mất kết nối, container orchestrator (Kubernetes, Docker Swarm) hay PaaS (Railway, Render) không thể phát hiện để khởi động lại hoặc ngắt routing traffic.
5. **Cố định cổng (Hardcoded Port) & Thiếu Graceful Shutdown:** Ứng dụng gán cứng port 8000 trong lệnh `uvicorn.run(..., port=8000)`, không lắng nghe biến môi trường `PORT` do platform cấp. Ngoài ra không có cơ chế bắt tín hiệu `SIGTERM` để hoàn tất các request đang xử lý trước khi tiến trình tắt.

### Exercise 1.3: Comparison table giữa Develop và Production

| Feature | Develop (`develop/app.py`) | Production (`production/app.py`) | Tại sao quan trọng? |
|---|---|---|---|
| **Config** | Hardcoded trong code (`PORT=8000`, `DEBUG=True`, API key giả lập) | Đọc hoàn toàn từ biến môi trường qua `os.getenv` / Dataclass / Pydantic Settings | Tuân thủ 12-Factor App; cùng một Docker image có thể triển khai trên dev, staging và prod chỉ bằng cách đổi env var mà không cần build lại. |
| **Health check** | Không có route kiểm tra trạng thái | Có tách biệt `GET /health` (Liveness) và `GET /ready` (Readiness) | Giúp container orchestrator và Load Balancer biết khi nào service còn sống (để restart nếu crash) và khi nào sẵn sàng phục vụ (để định tuyến traffic). |
| **Logging** | Dùng `print()`, log dạng plain text, in cả API key | Structured logging định dạng JSON (`ts`, `lvl`, `event`, `path`, `status`, `ms`) | Cho phép hệ thống tập trung log (ELK, Loki, CloudWatch) dễ dàng parse, filter, index và liên kết với distributed trace. Không in dữ liệu nhạy cảm. |
| **Shutdown** | Tắt đột ngột (kill process ngay lập tức) | Graceful shutdown xử lý tín hiệu `SIGTERM`, dùng FastAPI `lifespan` | Cho phép các request in-flight hoàn tất xử lý thành công (trả HTTP 200), đóng kết nối an toàn, tránh lỗi 502/504 Bad Gateway cho người dùng. |

---

## Part 2: Docker Containerization

### Exercise 2.1: Dockerfile questions
1. **Base image là gì?**  
   Base image trong `02-docker/develop/Dockerfile` là `python:3.11` (bản distribution đầy đủ, dung lượng ~1 GB). Trong bản production, base image tối ưu là `python:3.11-slim` để giảm thiểu kích thước và bề mặt tấn công.
2. **Working directory là gì?**  
   Working directory là `/app`, được thiết lập bởi chỉ thị `WORKDIR /app`. Mọi chỉ thị tiếp theo như `COPY`, `RUN`, `CMD` đều thực thi tương đối từ thư mục này bên trong container.
3. **Tại sao `COPY requirements.txt` trước `COPY . .`?**  
   Để tận dụng tối đa cơ chế **Docker Layer Caching**. Các dependencies trong `requirements.txt` thường ít thay đổi hơn so với mã nguồn ứng dụng. Bằng cách copy file `requirements.txt` và chạy `pip install` ở các layer trên, Docker sẽ tái sử dụng cache của layer đó khi mã nguồn thay đổi, giúp thời gian build các lần sau diễn ra gần như tức thì.
4. **`CMD` vs `ENTRYPOINT` khác nhau thế nào?**  
   - `ENTRYPOINT` xác định câu lệnh cố định luôn được thực thi khi container khởi chạy (đóng vai trò như executable chính của container).
   - `CMD` cung cấp các tham số mặc định cho `ENTRYPOINT`, hoặc định nghĩa lệnh mặc định nếu không có `ENTRYPOINT`. Các tham số của `CMD` có thể dễ dàng bị ghi đè bởi đối số truyền vào từ dòng lệnh `docker run <image> [command]`.

### Exercise 2.3: Image size comparison
- **Develop image (`python:3.11` single-stage):** `1010 MB` (~1.01 GB)
- **Production image (`python:3.11-slim` multi-stage):** `238 MB`
- **Chênh lệch (Difference):** Giảm `772 MB` (giảm `76.4%` dung lượng so với bản develop).
- **Lý do:** Multi-stage build tách riêng stage `builder` (chứa gcc, công cụ biên dịch) và stage `runtime` (chỉ copy các thư viện đã cài đặt sang bản slim gọn nhẹ), loại trừ cache và các gói không cần thiết.

### Exercise 2.4: Docker Compose stack
- **Kiến trúc hệ thống:**
  ```
  Client (Browser / Curl) ──▶ Nginx Load Balancer (:80 / :8080)
                                     │
                        ┌────────────┴────────────┐
                        ▼                         ▼
                  Agent Instance 1          Agent Instance 2
                        │                         │
                        └────────────┬────────────┘
                                     ▼
                                Redis Server (:6379)
  ```
- **Các services được khởi chạy:**
  1. `nginx`: Đóng vai trò Reverse Proxy & Load Balancer phân phối request theo thuật toán Round-Robin tới các backend agent.
  2. `agent`: Service chứa AI agent FastAPI, chạy nhiều replica (stateless).
  3. `redis`: Cơ sở dữ liệu in-memory lưu trữ session state, token bucket cho rate limiting và cost guard.
- **Kết quả kiểm tra qua Nginx:**
  ```bash
  $ curl -i http://localhost:8080/health
  HTTP/1.1 200 OK
  Content-Type: application/json
  {"status":"ok"}

  $ curl -i -X POST http://localhost:8080/ask -H "X-API-Key: day14-lab-key" -H "Content-Type: application/json" -d '{"question":"Hello"}'
  HTTP/1.1 200 OK
  Content-Type: application/json
  {"question":"Hello","answer":"..."}
  ```

---

## Part 3: Cloud Deployment

### Exercise 3.1 & 3.2: Railway & Render Deployment
- **Public URL:** `https://k5-l3a-day14-maituananh-2a202603574-deployment-b-production.up.railway.app`
- **So sánh `railway.toml` với `render.yaml`:**
  - `railway.toml`: Dùng cú pháp TOML, tập trung cấu hình build (`builder = "DOCKERFILE"`) và deploy runtime (`healthcheckPath = "/health"`, `restartPolicyType = "ON_FAILURE"`). Biến môi trường thường được quản lý trực tiếp qua Railway Dashboard hoặc CLI.
  - `render.yaml`: Dùng cú pháp YAML theo chuẩn Infrastructure as Code (Blueprint), cho phép định nghĩa toàn bộ hạ tầng gồm nhiều services (Web Service, Redis) trong cùng một file, hỗ trợ tạo secret tự động (`generateValue: true`) hoặc đồng bộ biến an toàn (`sync: false`).

### Exercise 3.3: GCP Cloud Run CI/CD Pipeline
Pipeline được khai báo trong `cloudbuild.yaml` gồm 4 giai đoạn tự động chạy khi push code:
1. **Step 1 (Test):** Sử dụng container `python:3.11-slim` để cài đặt dependencies và chạy bộ unit test với `pytest tests/`.
2. **Step 2 (Build):** Dùng `gcr.io/cloud-builders/docker` build Docker image từ Dockerfile, gắn tag theo `$COMMIT_SHA` và `:latest`, đồng thời tận dụng layer cache `--cache-from`.
3. **Step 3 (Push):** Push Docker image đã build lên Google Container Registry (GCR).
4. **Step 4 (Deploy):** Gọi Google Cloud Run để deploy image mới lên serverless container với cấu hình tự động co giãn (auto-scale), bảo mật HTTPS và zero-downtime rolling update.

---

## Part 4: API Security

### Exercise 4.1: API Key Authentication
- **Vị trí kiểm tra:** Header `X-API-Key` được kiểm tra thông qua FastAPI Dependency `Depends(verify_api_key)` trong `app/auth.py`.
- **Nếu sai hoặc thiếu key:** Hệ thống ngay lập tức trả về mã lỗi HTTP `401 Unauthorized` kèm JSON `{"detail": "Invalid or missing API key"}`.
- **Cách rotate key:** Cập nhật biến môi trường `AGENT_API_KEY` trên platform (Railway / Render / Docker Compose) mà không cần can thiệp hoặc sửa đổi mã nguồn.

### Exercise 4.2 & 4.3: Test Results
- **Trường hợp 1: Thiếu hoặc sai API Key (HTTP 401)**
  ```bash
  $ curl -i -X POST http://localhost:8000/ask -H "Content-Type: application/json" -d '{"question":"Hello"}'
  HTTP/1.1 401 Unauthorized
  content-type: application/json
  {"detail":"Invalid or missing API key"}
  ```

- **Trường hợp 2: Có API Key hợp lệ (HTTP 200)**
  ```bash
  $ curl -i -X POST http://localhost:8000/ask -H "X-API-Key: check-e50b5514f77c5ef2" -H "Content-Type: application/json" -d '{"question":"Hello"}'
  HTTP/1.1 200 OK
  content-type: application/json
  {"question":"Hello","answer":"Agent đang hoạt động tốt! (mock response) Hỏi thêm câu hỏi đi nhé."}
  ```

- **Trường hợp 3: Vượt quá giới hạn Rate Limit (HTTP 429)**
  ```bash
  $ for i in {1..10}; do curl -s -o /dev/null -w "%{http_code}\n" -X POST http://localhost:8000/ask -H "X-API-Key: check-e50b5514f77c5ef2" -H "Content-Type: application/json" -d '{"question":"Hello"}'; done
  200
  200
  200
  200
  200
  429
  429
  429
  429
  429
  ```
  Phản hồi chi tiết khi bị chặn 429:
  ```http
  HTTP/1.1 429 Too Many Requests
  retry-after: 60
  content-type: application/json
  {"detail":"Rate limit exceeded: 5 requests per minute"}
  ```

### Exercise 4.4: Cost Guard Implementation
Hệ thống tính toán chi phí ước tính dựa trên số lượng input tokens và output tokens cho mỗi lượt gọi LLM (`$0.00015/1K input tokens` và `$0.0006/1K output tokens`):
1. **Kiểm tra trước khi gọi (`check_budget`):** Đọc key `cost_guard:total_cost` trên Redis. Nếu tổng chi phí hiện tại vượt quá ngân sách cấu hình (`DAILY_BUDGET_USD` hoặc `MONTHLY_BUDGET_USD`), API lập tức từ chối với HTTP `402 Payment Required` trước khi gọi mô hình.
2. **Ghi nhận chi phí sau khi gọi (`record_cost`):** Tính toán chi phí thực tế của câu hỏi và câu trả lời, sau đó dùng lệnh nguyên tử `r.incrbyfloat("cost_guard:total_cost", cost)` trên Redis để đảm bảo tính đồng bộ trên tất cả worker và instance.

---

## Part 5: Scaling & Reliability

### Exercise 5.1: Health & Readiness Checks
- **Liveness Probe (`GET /health`):** Luôn trả về HTTP `200 OK` khi tiến trình FastAPI đang chạy, không phụ thuộc vào trạng thái kết nối tới Redis hay cơ sở dữ liệu bên ngoài. Khi endpoint này fail, platform sẽ tự động restart container.
- **Readiness Probe (`GET /ready`):** Kiểm tra các phụ thuộc cần thiết (gọi `r.ping()` tới Redis). Nếu Redis mất kết nối hoặc quá tải, trả về HTTP `503 Service Unavailable`. Khi đó load balancer sẽ tạm thời ngừng chuyển traffic tới instance này mà không restart container.

### Exercise 5.2: Graceful Shutdown
Sử dụng context manager `lifespan` của FastAPI kết hợp lắng nghe tín hiệu `SIGTERM`. Khi container nhận lệnh stop từ Docker/Kubernetes:
1. Web server ngừng nhận request mới.
2. Chờ các request đang trong quá trình xử lý (in-flight) hoàn thành và trả kết quả thành công cho client.
3. Đóng kết nối an toàn tới Redis và giải phóng tài nguyên.
4. Tiến trình tự động thoát với mã exit code `0` trong thời gian quy định (< 10 giây).

### Exercise 5.3: Stateless Design
- **Vấn đề của Stateful trong RAM:** Nếu lưu lịch sử hội thoại hoặc session trong biến toàn cục (dictionary trong RAM), khi có nhiều instance phía sau Load Balancer, các request tiếp theo của cùng một người dùng rơi vào instance khác sẽ bị mất toàn bộ ngữ cảnh trước đó.
- **Giải pháp Stateless với Redis:** Chuyển toàn bộ state (session data, conversation history, rate limit window) vào Redis. Mọi instance đều có thể truy xuất và cập nhật cùng một nguồn dữ liệu tập trung, cho phép mở rộng (scale out) lên hàng chục hoặc hàng trăm instance mà không xảy ra bất kỳ sai lệch nào.

### Exercise 5.4 & 5.5: Load Balancing & Stateless Verification
- Khi triển khai stack với 3 instances (`docker compose up --scale agent=3`), Nginx phân phối đều các request theo cơ chế round-robin.
- Kiểm tra kịch bản stateless: Gửi liên tiếp 5 câu hỏi trong cùng một session hội thoại, Nginx phân tán lần lượt tới các instance khác nhau nhưng dữ liệu hội thoại vẫn được bảo toàn đầy đủ nhờ Redis.

---

## Part 6: Final Project Deliverable Checklist

Kết quả chạy script chấm tự động `python check_production_ready.py`:

```text
================================================================
  Production Readiness Check — Day 14 Lab
================================================================

✅ 1. Dockerfile (multi-stage, < 500 MB)
     ✅ Dockerfile tồn tại
     ✅ requirements.txt tồn tại
     ✅ Multi-stage build (≥ 2 lệnh FROM)
     ✅ Base image gọn (slim / alpine / distroless) — stage cuối dùng python:3.11-slim
     ✅ Chạy bằng user non-root
     ✅ Có HEALTHCHECK
     ✅ Docker: build image thành công — 70s
     ✅ Docker: image < 500 MB — 238 MB
     ✅ Docker: container chạy được, GET /health → 200

✅ 2. docker-compose.yml (agent + redis)
     ✅ docker-compose.yml tồn tại
     ✅ Có service agent (build từ Dockerfile) + redis — services: agent, redis — đọc bằng docker compose config
     ✅ Service agent kết nối redis (REDIS_URL + depends_on)

✅ 3. .dockerignore
     ✅ .dockerignore tồn tại và có nội dung
     ✅ .dockerignore loại trừ .env (secrets)
     ✅ .dockerignore loại trừ __pycache__, venv

✅ 4. Health check endpoint (GET /health)
     ✅ Code có route /health
     ✅ Khi chạy: GET /health → 200 — uvicorn --workers 2

✅ 5. Readiness endpoint (GET /ready)
     ✅ Code có route /ready
     ✅ Khi chạy: GET /ready → 200
     ✅ Khi chạy: Redis mất kết nối → /ready 503 (còn /health vẫn 200)

✅ 6. API Key authentication
     ✅ Code đọc header X-API-Key
     ✅ Khi chạy: thiếu / sai API key → 401
     ✅ Khi chạy: API key đúng → 200

✅ 7. Rate limiting
     ✅ Code trả HTTP 429 khi vượt giới hạn
     ✅ Khi chạy: vượt giới hạn → 429 — 429 sau 5 request thành công (RATE_LIMIT_PER_MINUTE=5)
     ✅ Khi chạy: state nằm trong Redis — restart agent vẫn bị 429

✅ 8. Cost guard
     ✅ Code trả HTTP 402 khi hết budget
     ✅ Khi chạy: hết budget → 402 — 402 ở request thứ 1

✅ 9. Config từ environment variables
     ✅ app/config.py đọc biến môi trường
     ✅ .env.example liệt kê đủ biến cấu hình
     ✅ .env nằm trong .gitignore
     ✅ Không hard-code secret trong code
     ✅ Khi chạy: agent dùng AGENT_API_KEY và RATE_LIMIT_PER_MINUTE từ env

✅ 10. Structured logging
     ✅ Code ghi log dạng JSON
     ✅ Khi chạy: mọi dòng log của app là JSON hợp lệ — 12 dòng JSON

✅ 11. Graceful shutdown
     ✅ Code xử lý SIGTERM / lifespan shutdown
     ✅ Docker: `docker stop` tắt êm (exit code 0, < 10s) — exit code 0, 1.2s

✅ 12. Public URL ready (Railway / Render config)
     ✅ Có railway.toml hoặc render.yaml (không chỉ toàn comment)
     ✅ railway.toml: builder + healthcheckPath = "/health"
     ✅ render.yaml: web service + healthCheckPath /health
     ✅ render.yaml: secret không ghi thẳng giá trị (generateValue / sync: false)
     ✅ App lắng nghe theo biến PORT do platform cấp

================================================================
  📋 Checklist Deliverable
     ✅ Dockerfile (multi-stage, < 500 MB)
     ✅ docker-compose.yml (agent + redis)
     ✅ .dockerignore
     ✅ Health check endpoint (GET /health)
     ✅ Readiness endpoint (GET /ready)
     ✅ API Key authentication
     ✅ Rate limiting
     ✅ Cost guard
     ✅ Config từ environment variables
     ✅ Structured logging
     ✅ Graceful shutdown
     ✅ Public URL ready (Railway / Render config)
----------------------------------------------------------------
  Result: 12/12 tiêu chí đạt · 43/43 checks passed
  🎉 CHÚC MỪNG — project đạt đủ 12 tiêu chí production-ready!
================================================================
```

---

## AI Assistant Usage Log
- **Công cụ hỗ trợ:** Trợ lý ảo Antigravity AI (Google DeepMind).
- **Mục đích sử dụng:**
  1. Hỗ trợ rà soát mã nguồn, đối chiếu 12 tiêu chí đánh giá production-ready và thiết lập kiến trúc Docker multi-stage tối ưu.
  2. Viết các module bảo mật (API Key authentication, Redis sliding window rate limiter, cost guard) và cấu hình logging JSON chuẩn hóa.
  3. Tự động hóa quá trình chạy kiểm thử tải (load testing) và đánh giá độ chính xác (eval) trên golden dataset nhằm phát hiện và khắc phục các lỗ hổng tri thức (knowledge base).
- **Đánh giá hiệu quả:** Tăng tốc độ triển khai, đảm bảo tính tuân thủ quy chuẩn kỹ thuật của bài thi và không để xảy ra lỗi cú pháp hay bảo mật.
