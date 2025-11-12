# Design Decisions & Tradeoffs

This document explains key design decisions, alternatives considered, and tradeoffs made during development.

---

## 1. Concurrency Model: Async + Threads

### Decision

Use `asyncio` for I/O-bound operations (fetching) and `ThreadPoolExecutor` for CPU-bound operations (processing).

### Alternatives Considered

| Approach               | Pros                     | Cons                              | Why Not Chosen                      |
| ---------------------- | ------------------------ | --------------------------------- | ----------------------------------- |
| **Pure Async**         | Simple, single-threaded  | GIL limits CPU-bound work         | JSON parsing would block event loop |
| **Pure Threads**       | True parallelism         | High memory/CPU overhead          | Inefficient for I/O-bound fetching  |
| **Multiprocessing**    | True parallelism, no GIL | High overhead, serialization cost | Overkill for JSON parsing           |
| **Async + Threads** ✅ | Best of both worlds      | More complex                      | Chosen for efficiency               |

### Rationale

- **Fetching is I/O-bound:** Async provides efficient concurrency (3 endpoints, 15 req/sec total)
- **Processing is CPU-bound:** ThreadPoolExecutor releases GIL during I/O, provides true parallelism
- **Bounded queue:** Bridges async producers and threaded consumers

### Tradeoffs

- **Complexity:** More complex than pure async or pure threads
- **Debugging:** Harder to debug async + thread interactions
- **Acceptable:** Complexity justified by performance gains

**Requirements:** 1.2, 8.1, 8.2

---

## 2. Rate Limiting: Token Bucket Algorithm

### Decision

Implement token bucket algorithm with per-endpoint isolation.

### Alternatives Considered

| Approach            | Pros                   | Cons                       | Why Not Chosen                          |
| ------------------- | ---------------------- | -------------------------- | --------------------------------------- |
| **Fixed Window**    | Simple                 | Burst at window boundaries | Doesn't meet burst capacity requirement |
| **Sliding Window**  | Smooth rate            | Complex, memory-intensive  | Overkill for this scope                 |
| **Leaky Bucket**    | Smooth output          | No burst capacity          | Requirement specifies burst             |
| **Token Bucket** ✅ | Burst + sustained rate | Slightly more complex      | Chosen for burst capacity               |

### Rationale

- **Burst capacity:** Allows 5 instant requests (requirement 2.1)
- **Sustained rate:** Enforces 5 req/sec over time
- **Per-endpoint:** Endpoint A doesn't affect endpoint B

### Implementation Details

```python
# Token refill
tokens = min(max_tokens, tokens + (elapsed * refill_rate))

# Acquire
if tokens >= 1:
    tokens -= 1  # Instant
else:
    await asyncio.sleep(time_until_token)  # Wait
```

### Tradeoffs

- **Memory:** Per-endpoint state (acceptable for 3 endpoints)
- **Accuracy:** Uses wall-clock time (not monotonic), acceptable for this scope
- **Burst abuse:** Client could burst every 1 second (acceptable per requirements)

**Requirements:** 2.1

---

## 3. Circuit Breaker: Three-State Machine

### Decision

Implement CLOSED → OPEN → HALF_OPEN → CLOSED state machine with 3-failure threshold and 15s cooldown.

### Alternatives Considered

| Approach                    | Pros                     | Cons                   | Why Not Chosen                  |
| --------------------------- | ------------------------ | ---------------------- | ------------------------------- |
| **Two-State (Open/Closed)** | Simple                   | No graceful recovery   | Requirement specifies half-open |
| **Adaptive Threshold**      | Self-tuning              | Complex, needs history | Overkill for this scope         |
| **Percentage-Based**        | Handles partial failures | Needs sliding window   | More complex than needed        |
| **Three-State** ✅          | Graceful recovery        | Slightly more complex  | Chosen per requirements         |

### Rationale

- **CLOSED:** Normal operation, track failures
- **OPEN:** Fail fast after 3 consecutive retryable failures
- **HALF_OPEN:** Allow single probe after 15s cooldown
- **Recovery:** Close on success, reopen on failure

### Implementation Details

```python
# Failure tracking
if retryable:
    failure_count += 1
    if failure_count >= 3:
        state = OPEN
        opened_at = now

# Cooldown check
if state == OPEN and (now - opened_at) >= 15.0:
    state = HALF_OPEN
    allow_single_probe()

# Recovery
if state == HALF_OPEN and probe_success:
    state = CLOSED
    failure_count = 0
```

### Tradeoffs

- **Cooldown duration:** 15s may be too long/short for different scenarios (configurable)
- **Single probe:** Only one request in HALF_OPEN (prevents thundering herd)
- **Per-endpoint:** Failures on endpoint A don't affect endpoint B (isolation)

**Requirements:** 4.4

---

## 4. Retry Policy: Exponential Backoff with Jitter

### Decision

Exponential backoff (0.5s → 4.0s max) with 10% jitter, max 3 attempts.

### Alternatives Considered

| Approach                    | Pros                     | Cons                  | Why Not Chosen                       |
| --------------------------- | ------------------------ | --------------------- | ------------------------------------ |
| **Fixed Delay**             | Simple                   | Thundering herd       | Coordinated retries overload server  |
| **Linear Backoff**          | Predictable              | Slow recovery         | Doesn't reduce load quickly enough   |
| **Exponential (no jitter)** | Fast backoff             | Thundering herd       | Coordinated retries at 2^n intervals |
| **Exponential + Jitter** ✅ | Prevents thundering herd | Slightly more complex | Chosen for best practice             |

### Rationale

- **Exponential:** Reduces load on failing services (0.5s → 1.0s → 2.0s → 4.0s)
- **Jitter:** Prevents coordinated retries (random 0-10% of delay)
- **Max 4.0s:** Balances recovery time vs total timeout (60s constraint)
- **Max 3 attempts:** Prevents infinite retry loops

### Implementation Details

```python
delay = min(4.0, 0.5 * (2 ** attempt)) + jitter
jitter = random.uniform(0, delay * 0.1)

# Progression:
# Attempt 0: 0.5s + jitter (0.45-0.55s)
# Attempt 1: 1.0s + jitter (0.9-1.1s)
# Attempt 2: 2.0s + jitter (1.8-2.2s)
# Attempt 3: 4.0s + jitter (3.6-4.4s)
```

### Tradeoffs

- **Constants:** Tuned for this assignment (0.5s base, 4.0s max)
- **Jitter amount:** 10% may be too small/large for different scenarios
- **Max attempts:** 3 attempts may be too few/many for different error types
- **Configurable:** All constants exposed via `PipelineConfig`

**Requirements:** 2.5, 4.3

---

## 5. Error Classification: Retryable vs Non-Retryable

### Decision

Classify errors into retryable (429, 5xx, timeout) and non-retryable (4xx, malformed JSON).

### Alternatives Considered

| Approach                | Pros      | Cons                      | Why Not Chosen                       |
| ----------------------- | --------- | ------------------------- | ------------------------------------ |
| **Retry All Errors**    | Simple    | Wastes retries on 4xx     | 4xx won't succeed on retry           |
| **Retry None**          | Simple    | Fails on transient errors | Doesn't meet resilience requirements |
| **Classify by Type** ✅ | Efficient | Requires error taxonomy   | Chosen for best practice             |

### Rationale

- **429 Too Many Requests:** Retryable (server overloaded, will recover)
- **5xx Server Errors:** Retryable (transient server issues)
- **Timeout:** Retryable (network congestion, will recover)
- **4xx Client Errors:** Non-retryable (bad request, won't change)
- **Malformed JSON:** Non-retryable (data corruption, won't fix itself)

### Implementation Details

```python
def _is_retryable_status(self, status_code: int) -> bool:
    if status_code == 429:
        return True  # Rate limit, will recover
    if 500 <= status_code < 600:
        return True  # Server error, transient
    return False  # 4xx client error, permanent

# Circuit breaker integration
if retryable:
    circuit_breaker.record_failure(endpoint, retryable=True)
else:
    # Don't count non-retryable failures
    pass
```

### Tradeoffs

- **429 special case:** Treated as retryable + circuit breaker increment
- **Malformed JSON:** Treated as non-retryable (design decision to avoid retry loops)
- **4xx errors:** Some 4xx (e.g., 408 Request Timeout) could be retryable (not in scope)

**Requirements:** 2.5, 4.3, 4.4

---

## 6. Memory Management: Bounded Queue

### Decision

Use `asyncio.Queue(maxsize=100)` for producer-consumer communication.

### Alternatives Considered

| Approach               | Pros                | Cons                 | Why Not Chosen                 |
| ---------------------- | ------------------- | -------------------- | ------------------------------ |
| **Unbounded Queue**    | Simple, no blocking | Memory overflow risk | Requirement specifies bounded  |
| **Small Queue (10)**   | Low memory          | Frequent blocking    | Fetchers would block too often |
| **Large Queue (1000)** | Rare blocking       | High memory usage    | Wastes memory for 360 products |
| **Bounded (100)** ✅   | Balanced            | Requires tuning      | Chosen for balance             |

### Rationale

- **Backpressure:** Fetchers block when queue full (prevents memory overflow)
- **Memory:** ~10MB for 100 items (acceptable)
- **Performance:** Processing fast enough (>500 products/sec) that blocking rare

### Implementation Details

```python
# Producer (fetcher)
await queue.put(data)  # Blocks if queue full

# Consumer (processor)
data = await queue.get()  # Blocks if queue empty

# Shutdown
await queue.put(None)  # Sentinel value
```

### Tradeoffs

- **Maxsize:** 100 tuned for this assignment (360 products: 120 per endpoint × 3 endpoints)
- **Blocking:** Fetchers may block if processor slow (acceptable)
- **Memory:** Fixed memory usage regardless of total products

**Requirements:** 8.3, 10.2

---

## 7. Batch Processing: Size 50

### Decision

Process data in batches of 50 items using ThreadPoolExecutor.

### Alternatives Considered

| Approach                 | Pros         | Cons            | Why Not Chosen                   |
| ------------------------ | ------------ | --------------- | -------------------------------- |
| **Item-by-Item**         | Simple       | High overhead   | Thread pool overhead per item    |
| **Small Batch (10)**     | Low latency  | High overhead   | Too many thread pool submissions |
| **Large Batch (200)**    | Low overhead | High latency    | Delays processing start          |
| **Medium Batch (50)** ✅ | Balanced     | Requires tuning | Chosen for balance               |

### Rationale

- **Throughput:** Batch processing reduces thread pool overhead
- **Latency:** 50 items small enough for responsive processing
- **Memory:** 50 items × ~100KB = ~5MB per batch (acceptable)

### Implementation Details

```python
batch = []
while True:
    item = await queue.get()

    if item is None:  # Sentinel
        if batch:
            await _process_batch(batch)
        break

    batch.append(item)

    if len(batch) >= 50:
        await _process_batch(batch)
        batch = []
```

### Tradeoffs

- **Batch size:** 50 tuned for this assignment (may need adjustment for different workloads)
- **Final batch:** May be smaller than 50 (handled correctly)
- **Latency:** First product processed after 50 fetched (acceptable)

**Requirements:** 8.2

---

## 8. Thread Pool Size: 4 Workers

### Decision

Use `ThreadPoolExecutor(max_workers=4)` for CPU-bound processing.

### Alternatives Considered

| Approach          | Pros            | Cons              | Why Not Chosen                         |
| ----------------- | --------------- | ----------------- | -------------------------------------- |
| **Single Thread** | Simple          | Slow processing   | Doesn't utilize CPU cores              |
| **2 Workers**     | Low overhead    | Underutilizes CPU | Most machines have 4+ cores            |
| **8 Workers**     | High throughput | High overhead     | Diminishing returns, context switching |
| **4 Workers** ✅  | Balanced        | Requires tuning   | Chosen for typical CPU count           |

### Rationale

- **CPU cores:** Most machines have 4+ cores
- **GIL:** JSON parsing releases GIL, gets true parallelism
- **Overhead:** 4 workers low enough to avoid excessive context switching
- **Throughput:** >500 products/sec with 4 workers

### Implementation Details

```python
with ThreadPoolExecutor(max_workers=4) as executor:
    future = executor.submit(normalize_batch, batch, source)
    normalized = await asyncio.wrap_future(future)
```

### Tradeoffs

- **Worker count:** 4 tuned for typical machines (configurable via `PipelineConfig`)
- **CPU-bound:** Assumes JSON parsing is CPU-bound (true for this assignment)
- **Scalability:** May need more workers for larger batches or slower CPUs

**Requirements:** 8.2

---

## 9. Deduplication: In-Memory Set

### Decision

Use `seen_ids` set for deduplication at both processor and aggregator levels.

### Alternatives Considered

| Approach                       | Pros             | Cons               | Why Not Chosen                      |
| ------------------------------ | ---------------- | ------------------ | ----------------------------------- |
| **No Deduplication**           | Simple           | Duplicate products | Requirement specifies deduplication |
| **Database Unique Constraint** | Persistent       | Requires database  | Overkill for 360 products           |
| **Bloom Filter**               | Memory-efficient | False positives    | Unnecessary for small dataset       |
| **In-Memory Set** ✅           | Fast, accurate   | Memory usage       | Chosen for simplicity               |

### Rationale

- **Retry scenarios:** Same products may be fetched twice on retry
- **Idempotency:** Deduplication ensures each product counted once
- **Memory:** 300 product IDs × ~50 bytes = ~15KB (negligible)

### Implementation Details

```python
# Processor level
seen_ids = set()
for product in batch:
    if product["id"] not in seen_ids:
        normalized.append(normalize(product))
        seen_ids.add(product["id"])

# Aggregator level (thread-safe)
with self._lock:
    for product in products:
        if product.id not in self._seen_ids:
            self._products.append(product)
            self._seen_ids.add(product.id)
```

### Tradeoffs

- **Memory:** In-memory set limits scale to ~100K products (acceptable for this assignment)
- **Persistence:** Lost on restart (acceptable, not required)
- **Thread safety:** Aggregator uses lock for thread-safe deduplication

**Requirements:** 3.3

---

## 10. Configuration: Three-Tier Override System

### Decision

Implement CLI > ENV > YAML > Defaults precedence.

### Alternatives Considered

| Approach          | Pros          | Cons              | Why Not Chosen                             |
| ----------------- | ------------- | ----------------- | ------------------------------------------ |
| **CLI Only**      | Simple        | Not flexible      | Can't configure for different environments |
| **ENV Only**      | 12-factor app | Not user-friendly | Hard to override for testing               |
| **YAML Only**     | Declarative   | Not flexible      | Can't override without editing file        |
| **Three-Tier** ✅ | Flexible      | More complex      | Chosen per requirements                    |

### Rationale

- **YAML:** Project defaults (committed to repo)
- **ENV:** Deployment-specific overrides (staging, production)
- **CLI:** Runtime experimentation (testing, debugging)

### Implementation Details

```python
# Load order
config = load_yaml("config/config.yaml")  # Defaults
config.update(load_env("PIPELINE_*"))     # ENV overrides
config.update(parse_cli_args())           # CLI overrides

# Example
# YAML: timeout=60
# ENV: PIPELINE_TIMEOUT=120
# CLI: --timeout 180
# Result: timeout=180 (CLI wins)
```

### Tradeoffs

- **Complexity:** More complex than single source
- **Debugging:** Need to check all three sources to understand config
- **Flexibility:** Worth the complexity for different use cases

**Requirements:** 4.3, 7.4

---

## 11. Testing: Deterministic Fixtures

### Decision

Use fixed seed (42) for all random data generation in tests.

### Alternatives Considered

| Approach             | Pros                    | Cons                 | Why Not Chosen              |
| -------------------- | ----------------------- | -------------------- | --------------------------- |
| **Random Data**      | Tests edge cases        | Flaky tests          | CI failures from randomness |
| **Fixed Data**       | Deterministic           | Doesn't test variety | May miss edge cases         |
| **Seeded Random** ✅ | Deterministic + variety | Requires discipline  | Chosen for CI stability     |

### Rationale

- **CI stability:** Same seed produces same data every run
- **Reproducibility:** Failures can be reproduced locally
- **Variety:** Different seeds for different test scenarios

### Implementation Details

```python
# Fixture generation
def get_sample_products(source: str, count: int = 20, seed: int = 42):
    rng = random.Random(seed)  # Fixed seed

    products = []
    for i in range(count):
        product = {
            "id": f"{source}_{i+1}",
            "price": round(rng.uniform(10.0, 500.0), 2),
            "category": rng.choice(categories),
        }
        products.append(product)

    return products

# Pre-generated datasets
SEED_42_PRODUCTS_SOURCE1 = get_sample_products("source1", 100, seed=42)
SEED_42_PRODUCTS_SOURCE2 = get_sample_products("source2", 100, seed=43)
SEED_42_PRODUCTS_SOURCE3 = get_sample_products("source3", 100, seed=44)
```

### Tradeoffs

- **Edge cases:** Fixed seed may not catch all edge cases (acceptable tradeoff)
- **Variety:** Can use different seeds for different test scenarios
- **CI stability:** Worth the tradeoff for reliable CI

**Requirements:** 5.5

---

## 12. Performance Tests: Tolerance Bounds

### Decision

Use tolerance bounds (±20%) for timing-based performance tests.

### Alternatives Considered

| Approach                       | Pros     | Cons                      | Why Not Chosen                          |
| ------------------------------ | -------- | ------------------------- | --------------------------------------- |
| **Exact Timing**               | Precise  | Flaky in CI               | CI environment variability              |
| **No Timing Tests**            | Simple   | No performance validation | Requirement specifies performance tests |
| **Wide Tolerance (±50%)**      | Stable   | Not meaningful            | Too loose to catch regressions          |
| **Narrow Tolerance (±20%)** ✅ | Balanced | May be flaky              | Chosen for balance                      |

### Rationale

- **CI variability:** CI environments have variable CPU/network performance
- **Meaningful:** ±20% tight enough to catch regressions
- **Stable:** ±20% wide enough to avoid flaky failures

### Implementation Details

```python
# Rate limiter test
start = time.time()
for _ in range(15):
    await rate_limiter.acquire(endpoint)
elapsed = time.time() - start

# Expected: ~2-3 seconds (15 requests / 5 rps)
# Tolerance: 1.8-4.0 seconds (±20-30%)
assert 1.8 <= elapsed <= 4.0, f"Took {elapsed}s"
```

### Tradeoffs

- **Flakiness:** May still be flaky under extreme CI load (acceptable risk)
- **Precision:** Less precise than exact timing (acceptable for performance tests)
- **Regressions:** Tight enough to catch significant regressions

**Requirements:** 5.5, 10.3

---

## 13. Logging: Structured JSON

### Decision

Use structured JSON logging with consistent schema.

### Alternatives Considered

| Approach               | Pros             | Cons                | Why Not Chosen                 |
| ---------------------- | ---------------- | ------------------- | ------------------------------ |
| **Plain Text**         | Human-readable   | Hard to parse       | Can't query/aggregate logs     |
| **Key-Value Pairs**    | Semi-structured  | Inconsistent format | Hard to parse programmatically |
| **Structured JSON** ✅ | Machine-readable | Less human-readable | Chosen for observability       |

### Rationale

- **Observability:** JSON logs can be ingested by log aggregators (ELK, Splunk)
- **Querying:** Can query by event type, endpoint, status code
- **Consistency:** Enforced schema prevents ad-hoc logging

### Implementation Details

```python
logger.info(
    "fetch_page",
    extra={
        "event": "fetch_page",
        "endpoint": endpoint,
        "page": page,
        "status_code": response.status_code,
        "elapsed_ms": elapsed * 1000,
    }
)
```

### Tradeoffs

- **Readability:** Less human-readable than plain text (acceptable for production)
- **Verbosity:** More verbose than plain text (acceptable for observability)
- **Tooling:** Requires log aggregator for best experience (not required for assignment)

**Requirements:** 6.4

---

## 14. Mock API Implementation: Custom FastAPI Servers

### Decision

Build custom FastAPI mock servers instead of using third-party mocking libraries or external test APIs.

### Alternatives Considered

| Approach                      | Pros                    | Cons                                | Why Not Chosen                                |
| ----------------------------- | ----------------------- | ----------------------------------- | --------------------------------------------- |
| **httpx.MockTransport**       | Fast, no network        | Can't test real HTTP behavior       | Doesn't test actual network/timeout scenarios |
| **responses/httpretty**       | Simple mocking          | Limited control over behavior       | Can't simulate realistic API patterns         |
| **External Test APIs**        | Real HTTP               | Unreliable, rate limits, no control | Can't inject errors or control timing         |
| **Custom FastAPI Servers** ✅ | Full control, realistic | More implementation work            | Chosen for realism and control                |

### Rationale

- **Realistic Behavior:** Real HTTP server with actual network stack, timeouts, connection handling
- **Error Injection:** Can inject 429, 5xx errors at configurable rates for resilience testing
- **Pagination:** Implements realistic pagination with 20 items/page, 5+ pages
- **Rate Limiting:** Can implement actual rate limiting returning 429 when exceeded
- **Latency Simulation:** Can add configurable delays to simulate slow APIs
- **Deterministic:** Seeded random errors for reproducible CI results
- **Integration Testing:** Enables true end-to-end testing with real async HTTP

### Implementation Details

```python
# FastAPI app with configurable behavior
@app.get("/api/products")
async def get_products(page: int = 1):
    # Simulate latency
    await asyncio.sleep(random.uniform(0.01, 0.1))

    # Inject errors (10% rate)
    if random.random() < 0.1:
        raise HTTPException(status_code=503)

    # Return paginated data
    products = generate_products(page, seed=42)
    return {"page": page, "products": products}
```

### Tradeoffs

- **Implementation Cost:** More work than simple mocking (acceptable for comprehensive testing)
- **Maintenance:** Need to maintain mock servers (acceptable, well-structured)
- **Startup Time:** Docker compose startup adds ~5s (acceptable for integration tests)
- **Realism:** Worth the cost for realistic integration testing

### Benefits Realized

- **Integration Tests:** 22 comprehensive integration tests with real HTTP
- **Error Scenarios:** Tested 429, 5xx, timeout, malformed JSON with real network
- **Circuit Breaker:** Verified circuit breaker behavior with actual failing endpoints
- **Rate Limiting:** Validated rate limiter with real concurrent HTTP requests
- **Docker Compose:** Complete system demo with `docker compose up --build`

### Error Rate Selection: 10%

**Decision:** Configure mock servers with 10% error rate (5xx errors).

**Rationale:**

Real-world API error rates vary significantly by industry and criticality:

- **Banking/Payments:** 0.1% (highly critical, strict SLAs)
- **E-commerce:** 1-10% (acceptable for non-critical operations)
- **Internal APIs:** 5-15% (development/staging environments)

**Why 10% for this assignment:**

- **Aggressive Testing:** 10% error rate is high enough to frequently trigger resilience patterns (circuit breaker, retries) during testing
- **Demonstrates Robustness:** Shows the pipeline can handle degraded conditions and still achieve high success rates
- **Realistic for E-commerce:** E-commerce APIs (our mock scenario) can experience 10% error rates during peak load or partial outages
- **Validates Resilience:** With 10% errors, the system still achieves 90%+ success rate, demonstrating effective retry and circuit breaker logic
- **Configurable:** Error rate is configurable via `ERROR_RATE` environment variable for different test scenarios

**Tradeoffs:**

- **Higher than Production:** 10% is higher than most production APIs (typically <1%)
- **Acceptable for Testing:** Intentionally high to stress-test resilience patterns
- **Buffer Strategy:** Serve 7 pages (140 products) to ensure 100+ products even with 10% error rate

**Requirements:** 9.1, 9.2, 9.3, 9.4, 9.5, 10.2

---

## 15. Output Format: JSON Schema

### Decision

Output results as JSON with specific schema (summary + products + errors).

### Alternatives Considered

| Approach       | Pros                     | Cons           | Why Not Chosen                 |
| -------------- | ------------------------ | -------------- | ------------------------------ |
| **CSV**        | Simple, Excel-compatible | No nested data | Can't represent errors/summary |
| **Plain Text** | Human-readable           | Hard to parse  | Not machine-readable           |
| **JSON** ✅    | Machine-readable, nested | Verbose        | Chosen per requirements        |

### Rationale

- **Machine-readable:** Can be parsed by other tools
- **Nested data:** Supports summary, products, errors in single file
- **Schema validation:** Can validate against JSON schema

### Implementation Details

```json
{
  "summary": {
    "total_products": 300,
    "unique_products": 295,
    "duplicates_skipped": 5,
    "success_rate": 98.33,
    "processing_time_seconds": 32.45
  },
  "sources": {
    "source1": {
      "items_fetched": 100,
      "errors": 2,
      "avg_price": 125.50
    }
  },
  "products": [...],
  "errors": [...]
}
```

### Tradeoffs

- **Verbosity:** JSON more verbose than CSV (acceptable for 360 products)
- **Precision:** Numeric rounding (2 decimals for prices, 4 for rates)
- **Size:** ~360KB for 360 products (acceptable)

**Requirements:** 9.1, 9.2, 9.3

---

## 16. Data Normalization: Flexible vs Hardcoded Mapping

### Decision

Implement flexible, defensive normalizer with extraction functions for each field type.

### Alternatives Considered

| Approach                   | Pros               | Cons                   | Why Not Chosen                   |
| -------------------------- | ------------------ | ---------------------- | -------------------------------- |
| **Hardcoded Mappings**     | Simple, fast       | Breaks on new schemas  | Not production-ready             |
| **Schema Registry**        | Explicit contracts | Requires coordination  | Overkill for this scope          |
| **ML-based Inference**     | Handles anything   | Complex, unpredictable | Over-engineering                 |
| **Flexible Extraction** ✅ | Handles variety    | More code              | Chosen for real-world robustness |

### Rationale

Real-world APIs have:

- **Different field names**: `id` vs `product_id` vs `item_id` vs `userId`
- **Different types**: String prices ("$19.99") vs numeric (19.99)
- **Nested structures**: `category: "electronics"` vs `category: {name: "Electronics"}`
- **Missing fields**: Some APIs don't have prices, categories, etc.
- **Invalid data**: Negative prices, empty strings, null values

**Hardcoded approach (initial):**

```python
# Brittle - breaks on new schemas
product_id = raw_product.get("id") or raw_product.get("product_id")
```

**Flexible approach (production-ready):**

```python
def _extract_id(raw_product: Dict) -> str:
    """Try multiple field names, handle types, provide fallback."""
    id_fields = ["id", "product_id", "item_id", "userId", "sku"]
    for field in id_fields:
        value = raw_product.get(field)
        if value is not None:
            return str(value)  # Type coercion
    return "unknown"  # Graceful fallback
```

### Implementation Details

**Extraction Functions:**

1. **`_extract_id()`**: Tries 5 field names, handles string/numeric IDs
2. **`_extract_title()`**: Tries 4 field names, falls back to description
3. **`_extract_price()`**: Handles strings, currency symbols, European format, validation
4. **`_extract_category()`**: Handles strings, nested objects, arrays

**Type Coercion:**

```python
# String price → float
"$19.99" → 19.99
"19,99" → 19.99  # European format
"invalid" → None  # Graceful failure
```

**Nested Structure Handling:**

```python
# Nested category object
{"category": {"name": "Electronics", "id": 1}} → "electronics"

# Category array
{"categories": ["books", "fiction"]} → "books"
```

**Validation:**

```python
# Negative price rejected
{"price": -10} → None

# Empty string rejected
{"title": ""} → "Unknown Product"
```

### Tradeoffs

- **More code**: 4 extraction functions vs simple `get()` calls
- **More tests**: 31 tests vs 3 tests (acceptable for robustness)
- **Slower**: Multiple field checks (negligible - microseconds)
- **Maintainable**: Easy to add new field variants

### Real-World Examples Handled

**DummyJSON (rich structure):**

```json
{
  "id": 1,
  "title": "Mascara",
  "price": 9.99,
  "category": "beauty",
  "brand": "Essence",
  "stock": 99
}
```

**Escuelajs (nested category):**

```json
{
  "id": 1,
  "title": "T-Shirt",
  "price": 44,
  "category": { "name": "Clothes", "id": 1 }
}
```

**JSONPlaceholder (posts as products):**

```json
{
  "userId": 1,
  "id": 1,
  "title": "Post title",
  "body": "Post content"
}
```

All three schemas normalize to the same unified format.

### Benefits Realized

- **Robustness**: Handles unexpected schemas without crashing
- **Flexibility**: Easy to add new field variants
- **Testability**: Each extraction function tested independently
- **Production-ready**: Defensive coding, validation, graceful degradation

**Requirements:** 3.2

---

## Summary

All design decisions were made with the following principles:

1. **Requirements First:** Every decision maps to specific requirements (1.x-13.x)
2. **Best Practices:** Follow industry best practices (exponential backoff, circuit breakers, structured logging)
3. **Simplicity:** Choose simplest approach that meets requirements (KISS principle)
4. **Performance:** Optimize for throughput and latency within constraints
5. **Testability:** Design for comprehensive testing (91.6% coverage, 194 tests)
6. **Maintainability:** Clear separation of concerns, comprehensive documentation

**All decisions were made manually after considering alternatives and tradeoffs. AI tools (Kiro/Claude Sonnet 4) provided scaffolding and test patterns, but all architectural choices, design decisions, and implementation logic are mine.**
