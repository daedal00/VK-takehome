# Design Decisions & Tradeoffs



---

## 1. Concurrency Model: Async + Threads

**Decision:** `asyncio` for I/O-bound fetching, `ThreadPoolExecutor` for CPU-bound processing.

**Why:** Async provides efficient concurrency for HTTP requests (3 endpoints, 15 req/sec total). ThreadPoolExecutor releases GIL during I/O, provides true parallelism for JSON parsing. Bounded queue bridges async producers and threaded consumers.

**Tradeoff:** More complex than pure async, but performance gains justify it.

---

## 2. Rate Limiting: Token Bucket

**Decision:** Token bucket algorithm with per-endpoint isolation (5 tokens, refill 5/sec).

**Why:** Allows burst capacity (5 instant requests) + sustained rate (5 req/sec). Per-endpoint isolation means endpoint A doesn't affect endpoint B.

**Tradeoff:** Slightly more complex than fixed window, but requirement specifies burst capacity.

---

## 3. Circuit Breaker: Three-State Machine

**Decision:** CLOSED → OPEN (after 3 retryable failures) → HALF_OPEN (after 15s cooldown) → CLOSED/OPEN.

**Why:** Prevents cascading failures. Half-open state allows graceful recovery with single probe request.

**Tradeoff:** 15s cooldown may be too long/short for different scenarios (configurable via `PipelineConfig`).

---

## 4. Retry Policy: Exponential Backoff + Jitter

**Decision:** Exponential backoff (0.5s → 4.0s max) with 10% jitter, max 3 attempts.

**Why:** Reduces load on failing services. Jitter prevents thundering herd (coordinated retries).

**Tradeoff:** Constants tuned for this assignment; exposed via config for flexibility.

---

## 5. Error Classification: Retryable vs Non-Retryable

**Decision:** Retry 429/5xx/timeout; skip 4xx/malformed JSON.

**Why:** 429/5xx are transient (server will recover). 4xx are permanent (bad request won't change). Malformed JSON is data corruption (won't fix itself).

**Tradeoff:** Some 4xx (e.g., 408 Request Timeout) could be retryable (not in scope).

---

## 6. Memory Management: Bounded Queue

**Decision:** `asyncio.Queue(maxsize=100)` for producer-consumer communication.

**Why:** Prevents memory overflow when fetchers produce faster than processor consumes. Provides backpressure to slow down fetchers.

**Tradeoff:** Fetchers may block if processor slow (acceptable - processing is fast >500 products/sec).

---

## 7. Batch Processing: Size 50

**Decision:** Process data in batches of 50 items using ThreadPoolExecutor.

**Why:** Batch processing reduces thread pool overhead. 50 items balances throughput (low overhead) and latency (responsive processing).

**Tradeoff:** Batch size tuned for this assignment; configurable via `PipelineConfig`.

---

## 8. Thread Pool Size: 4 Workers

**Decision:** `ThreadPoolExecutor(max_workers=4)` for CPU-bound processing.

**Why:** Most machines have 4+ cores. JSON parsing releases GIL, gets true parallelism. 4 workers low enough to avoid excessive context switching.

**Tradeoff:** Worker count tuned for typical machines; configurable via `PipelineConfig`.

---

## 9. Data Normalization: Flexible vs Hardcoded

**Decision:** Flexible extraction functions for each field type (ID, title, price, category).

**Why:** Real-world APIs have different field names, types, nested structures. Flexible normalizer handles:

- Different field names (id vs product_id vs item_id)
- Different types (string prices vs numeric)
- Nested structures (category objects vs strings)
- Missing fields (graceful defaults)

**Tradeoff:** More code (4 extraction functions) but production-ready robustness.

**Example:**

```python
# Handles all these variants
_extract_price({"price": 19.99}) → 19.99
_extract_price({"cost": "$19.99"}) → 19.99
_extract_price({"price": "19,99"}) → 19.99  # European
_extract_category({"category": "Electronics"}) → "electronics"
_extract_category({"category": {"name": "Electronics"}}) → "electronics"
```

---

## 10. Mock Servers: Custom FastAPI vs External APIs

**Decision:** Build custom FastAPI mock servers instead of using external test APIs.

**Why:**

- **Control:** Can inject errors, control timing, configure behavior
- **Deterministic:** Fixed seeds for reproducible CI results
- **Realistic:** Real HTTP server with actual network stack, timeouts
- **Integration:** Enables true end-to-end testing

**Tradeoff:** More implementation work (acceptable for comprehensive testing).

---

## 11. Configuration: Three-Tier Override System

**Decision:** CLI flags > ENV vars > YAML > Defaults.

**Why:**

- **YAML:** Project defaults (committed to repo)
- **ENV:** Deployment-specific overrides (staging, production)
- **CLI:** Runtime experimentation (testing, debugging)

**Tradeoff:** More complex than single source, but flexible for different use cases.

---

## 12. Testing: Deterministic Fixtures

**Decision:** Fixed seed (42) for all random data generation in tests.

**Why:** Same seed produces same data every run. Failures can be reproduced locally. CI stability.

**Tradeoff:** Fixed seed may not catch all edge cases (acceptable for CI stability).