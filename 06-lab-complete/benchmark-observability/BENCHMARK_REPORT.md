# Benchmark & Observability Report — Day 14

> Mọi con số được lấy từ report JSON / CSV / screenshot thật, không ước lượng.

**Họ tên:** Mai Tuấn Anh (MSSV: 2A202603574)
**Ngày chạy:** 2026-11-25
**Môi trường:** Windows 11, Docker Desktop 4 CPU / 8GB RAM, Python 3.12.4

---

## 1. SLO của agent

| SLI | SLO | Lý do chọn ngưỡng này |
|---|---|---|
| p95 latency `/ask` | < 500 ms | 500ms là ngưỡng mà người dùng bắt đầu cảm thấy chờ lâu. Với mock LLM baseline ~200ms, SLO 500ms cho phép buffer 2.5x để hấp thụ tail latency mà vẫn đảm bảo trải nghiệm tốt. |
| Error rate `/ask` | < 2% | Cho phép tỉ lệ lỗi nhỏ do transient failure (503 từ mock), nhưng vẫn đảm bảo 98% request thành công — đủ tin cậy cho production. |
| Accuracy trên golden dataset | ≥ 85% | Agent cần trả lời đúng ít nhất 85% câu hỏi trong golden dataset để đảm bảo chất lượng kiến thức. Ngưỡng 80% là quality gate tối thiểu, 85% cho thêm margin an toàn. |

---

## 2. Benchmark hiệu năng (develop, `load_test.py`)

### 2.1 Concurrency vs latency (agent v2)

| Concurrency | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Error rate | SLO |
|---|---|---|---|---|---|---|
| 1 | 3.89 | 202.6 | 237.9 | 1710.8 | 0.67% | ✅ PASS |
| 10 | 41.59 | 188.8 | 237.3 | 1690.0 | 0% | ✅ PASS |
| 50 | 87.38 | 219.5 | 579.9 | 1738.1 | 2% | ❌ FAIL |
| 100 | 38.78 | 1069.5 | 5400.4 | 5648.5 | 2.67% | ❌ FAIL |

**Nhận xét:** RPS **không** tăng tuyến tính theo concurrency. Từ c=1 đến c=10, RPS tăng gần tuyến tính (3.89 → 41.59, ~10.7x) vì server chưa bão hòa. Từ c=10 lên c=50, RPS tăng lên 87.38 (chỉ ~2.1x thay vì 5x). Ở c=100, RPS **giảm** xuống 38.78 — hiệu ứng "contention collapse": khi quá nhiều request đồng thời, thời gian chờ hàng đợi tăng vọt (p50 lên 1069ms, p95 lên 5400ms), server bị overload và throughput giảm. Điều này cho thấy sweet spot của agent đơn instance nằm quanh c=10-50.

### 2.2 Tail latency

| `MOCK_SLOW_RATE` | avg (ms) | p95 (ms) | p99 (ms) |
|---|---|---|---|
| 0 | 212.5 | 456.0 | 513.4 |
| 0.03 (mặc định) | 271.7 | 518.4 | 1711.1 |
| 0.1 | 320.1 | 1689.9 | 1728.2 |

**Nhận xét:** Chỉ số **p95 và p99** nhạy nhất với request chậm. Khi tăng `MOCK_SLOW_RATE` từ 0 lên 0.1, avg chỉ tăng 51% (212.5 → 320.1 ms) nhưng p99 tăng **237%** (513.4 → 1728.2 ms). Điều này chứng minh tại sao SLO không nên đặt theo average: average bị "san phẳng" bởi đa số request nhanh, che giấu hoàn toàn tail latency — những request chậm nhất mà người dùng thực sự trải nghiệm. SLO phải dùng percentile (p95/p99) để phản ánh đúng worst-case experience.

---

## 3. Benchmark chất lượng (develop, `eval/run_eval.py`)

| Chỉ số | Agent v1 | Agent v2 | Agent v2 (sau khi sửa KB) |
|---|---|---|---|
| Accuracy | 4.3% (1/23) | 91.3% (21/23) | 100% (23/23) |
| Avg tokens / câu | 57.4 | 109.1 | 113.7 |
| Tổng cost (USD) | $0.000408 | $0.000762 | $0.000790 |
| Cost / câu đúng (USD) | $0.000408 | $0.0000363 | $0.0000344 |
| Quality gate | ❌ FAIL | ✅ PASS | ✅ PASS |

**Những câu v2 trả lời sai ban đầu và cách bạn đã sửa:**

| ID | Keyword bị thiếu | Bạn đã sửa gì |
|---|---|---|
| scaling-03 | `cpu`, `memory`, `custom metrics` | Thêm entry về HPA/Kubernetes vào `KNOWLEDGE_BASE` trong `mock_llm.py`: *"Kubernetes HPA (Horizontal Pod Autoscaler) scale số pod dựa trên cpu, memory hoặc custom metrics như RPS hay độ dài hàng đợi."* |
| security-02 | `token`, `hết hạn`, `chữ ký` | Thêm entry về JWT vào `KNOWLEDGE_BASE` trong `mock_llm.py`: *"API key là chuỗi bí mật cố định, không tự hết hạn. JWT là token có chữ ký số, chứa thông tin user và thời điểm hết hạn; server xác minh chữ ký mà không cần tra cứu database."* |

**Nhận xét về trade-off chất lượng / chi phí / latency giữa v1 và v2:**

- **Chất lượng:** v2 vượt trội hoàn toàn — accuracy từ 4.3% lên 91.3% (và 100% sau khi sửa KB). v1 trả lời chung chung, không có kiến thức chuyên môn.
- **Chi phí:** v2 tốn gần gấp đôi tokens (109.1 vs 57.4 tokens/câu) và tổng cost ($0.000762 vs $0.000408). Tuy nhiên, **cost per correct answer** của v2 thấp hơn 11x ($0.0000363 vs $0.000408) — vì v1 gần như không trả lời đúng câu nào.
- **Latency:** Latency tương đương vì cả hai dùng cùng mock LLM. Trong thực tế, v2 có thể chậm hơn do sinh nhiều token hơn.
- **Kết luận:** Chấp nhận tăng nhẹ chi phí để có chất lượng cao hơn nhiều là trade-off hoàn toàn xứng đáng. Cost per correct answer mới là metric quan trọng, không phải tổng cost.

---

## 4. Observability stack (production)

### 4.1 Screenshot

- [x] Dashboard Grafana khi đang có tải (thấy rõ Golden Signals) — `screenshots/grafana-dashboard.png`
- [x] Một trace chậm trong Jaeger (thấy span nào chiếm thời gian) — `screenshots/jaeger-slow-trace.png`
- [x] Một trace lỗi trong Jaeger (có event `exception`) — `screenshots/jaeger-error-trace.png`
- [x] Trang Alerts của Prometheus với ít nhất 1 alert đang **firing** — `screenshots/prometheus-alert-firing.png`

### 4.2 Thí nghiệm "phá hệ thống"

| # | Thay đổi | Alert nào firing | Thời gian từ lúc đổi → firing | Panel nào phản ánh rõ nhất |
|---|---|---|---|---|
| A | `MOCK_ERROR_RATE=0.2` | `HighErrorRate` | ~1-2 phút (cần tích lũy error budget) | Error Rate panel — tỉ lệ 5xx tăng vọt |
| B | `MOCK_SLOW_RATE=0.3` | `HighP95Latency` | ~2-3 phút (p95 vượt 500ms) | Latency panel — p95/p99 tăng rõ rệt |
| C | `LLM_MODEL=mock-llm-large` | `LLMCostBurnRateHigh` | ~1 phút (cost rate tăng ngay) | Cost panel — burn rate vượt ngưỡng |
| D | `docker pause` 1 instance | `AgentInstanceDown` | ~15-30 giây (Prometheus scrape thấy target down) | Instance Health panel — 1 target bị down |
| E | `AGENT_VERSION=v1` | Không có alert nào firing | — | Không panel nào thay đổi đáng kể |

**Thí nghiệm E không làm alert nào firing. Bạn sẽ phát hiện loại sự cố này trong production bằng cách nào?**

`AGENT_VERSION=v1` không làm thay đổi metrics về latency, error rate hay cost — vì mock LLM vẫn hoạt động bình thường, chỉ chất lượng câu trả lời giảm (accuracy từ 100% xuống 4.3%). Đây là loại **silent degradation** — hệ thống vẫn "xanh" nhưng output kém chất lượng.

Cách phát hiện:
1. **Quality gate trong CI/CD pipeline:** Chạy `eval/run_eval.py` với golden dataset trước mỗi lần deploy. Nếu accuracy < 80%, block deployment.
2. **Canary deployment:** Deploy v1 cho 5% traffic, so sánh user satisfaction metrics (thumbs up/down) với v2.
3. **Online eval:** Sampling một phần response, chạy LLM-as-judge hoặc human review để phát hiện regression chất lượng theo thời gian thực.
4. **Custom metric:** Thêm Prometheus metric `agent_response_quality_score` từ periodic eval, đặt alert khi score giảm.

### 4.3 Debug bằng trace

Chọn 1 trace chậm nhất tìm được:

- `trace_id`: `45e43e737bb16ce57dd13737411f9209`
- Tổng thời gian: 1793 ms
- Span chiếm nhiều thời gian nhất: `llm_generate` (1650 ms, ~92%)
- Dòng log tương ứng (grep theo `trace_id`):

```json
{"timestamp": "2026-11-25T08:40:12.345Z", "level": "INFO", "message": "request completed", "trace_id": "45e43e737bb16ce57dd13737411f9209", "duration_ms": 1793, "status": 200, "path": "/ask"}
```

**Phân tích:** Span `llm_generate` chiếm 92% tổng thời gian request. Đây là request bị mock LLM "slow path" (simulate latency cao). Các span khác (`auth`, `rate_limit`, `knowledge_search`) chỉ chiếm vài ms. Nút thắt rõ ràng là LLM inference — trong production thật, cần cân nhắc caching, streaming response, hoặc dùng model nhỏ hơn cho các câu hỏi đơn giản.

---

## 5. Benchmark scaling (production, Locust headless, 100 users, 2 phút)

| Số instance | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Failures |
|---|---|---|---|---|---|
| 1 | 58.52 | 200 | 620 | 1700 | 71 (0.93%) |
| 3 (*) | 59.74 | 200 | 320 | 1700 | 76 (0.97%) |

> (*) Ghi chú: Scale test với `--scale agent=3` thực tế chạy 2 instance do Docker Compose lifecycle. Kết quả vẫn cho thấy cải thiện rõ rệt so với 1 instance.

**Giải thích kết quả:**

Scale **có** cải thiện p95 đáng kể: từ 620ms (1 instance) xuống 320ms (2+ instance) — giảm **48%**. Điều này cho thấy ở 1 instance, hàng đợi request bị dồn lại khiến p95 cao; thêm instance giúp phân tải qua Nginx round-robin, giảm wait time.

Tuy nhiên, **RPS và p99 gần như không đổi** (58.52 vs 59.74 RPS, p99 = 1700ms ở cả hai). Nút thắt nằm ở:

1. **LLM latency (bottleneck chính):** Mock LLM có baseline ~200ms và slow path ~1700ms. Thêm instance không giảm được latency của từng request — chỉ giảm queue wait time.
2. **p99 không giảm** vì 1-3% request luôn gặp slow path (MOCK_SLOW_RATE=0.03), đây là giới hạn của LLM chứ không phải của infrastructure.
3. **RPS bão hòa** do Locust chỉ gửi 100 users và mock LLM có throughput giới hạn — thêm instance chỉ giúp khi demand vượt capacity của 1 instance.

**Kết luận:** Horizontal scaling giải quyết tốt vấn đề queuing (p95), nhưng không giải quyết được latency nội tại của LLM (p99). Muốn cải thiện p99, cần optimize ở tầng model (caching, model selection, timeout).

---

## 6. Kết luận

- 3 điều học được về benchmark & observability:
  1. **Average là chỉ số lừa dối.** Trong load test, avg latency chỉ tăng nhẹ khi thêm slow request, nhưng p95/p99 tăng gấp 3-4 lần. SLO phải đặt theo percentile để bảo vệ trải nghiệm của người dùng ở "tail" — những người chờ lâu nhất.
  2. **Observability ba trụ cột (metrics + traces + logs) bổ sung cho nhau.** Prometheus alert phát hiện "có gì đó sai" (p95 tăng), Jaeger trace chỉ ra "span nào chậm" (llm_generate 92%), và structured log cho context cụ thể (request_id, trace_id). Thiếu một trụ nào cũng khiến debug trở nên mù mờ.
  3. **Không phải mọi degradation đều trigger alert.** Thí nghiệm E (AGENT_VERSION=v1) chứng minh rằng quality degradation "im lặng" — hệ thống vẫn healthy nhưng output kém. Cần kết hợp runtime monitoring với offline eval (golden dataset, quality gate) trong CI/CD để phát hiện toàn diện.

- Nếu đưa agent này lên production thật, sẽ thêm metric / alert:

  1. **`agent_response_quality_score` (Gauge):** Chạy periodic eval sampling 1% response, đặt alert khi score < 0.85 trong 10 phút.
  2. **`llm_token_usage_total` (Counter) theo model:** Theo dõi token consumption theo thời gian thực, alert khi burn rate vượt daily budget 80%.
  3. **`agent_cache_hit_ratio` (Gauge):** Nếu thêm caching, monitor hit ratio — alert khi < 50% (cache hiệu quả thấp hoặc bị invalidate sai).
  4. **`request_queue_depth` (Gauge):** Đo số request đang chờ xử lý, alert khi > 100 liên tục 1 phút — dấu hiệu cần scale out.
  5. **End-to-end latency budget breakdown dashboard:** Hiển thị % thời gian của mỗi span (auth, rate_limit, knowledge_search, llm_generate) để nhanh chóng identify bottleneck khi latency tăng.
