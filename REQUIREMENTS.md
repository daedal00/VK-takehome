# Requirements

Concise mapping to challenge requirements with reference numbers.

---

## 1. Data Fetching (Async/Concurrent)

- **1.1** Fetch from 3 mock API endpoints concurrently
- **1.2** Implement rate limiting: 5 requests/second per endpoint
- **1.3** Handle timeouts: connect 3s, read 8s
- **1.4** Retry on failures: max 3 attempts with exponential backoff (0.5s → 4.0s)
- **1.5** Pagination: 20 items/page, 100+ products per endpoint

---

## 2. Data Processing (Multithreading/Worker Pool)

- **2.1** Use ThreadPoolExecutor for CPU-bound processing
- **2.2** Normalize data from different APIs to unified schema
- **2.3** Calculate metrics (average price per source, category distribution)
- **2.4** Implement thread-safe synchronization for shared data

---

## 3. Error Handling & Resilience

- **3.1** Gracefully handle API failures (partial failures don't crash pipeline)
- **3.2** Implement circuit breaker pattern (3 failures → 15s cooldown → half-open probe)
- **3.3** Log errors with appropriate detail levels
- **3.4** Classify errors: retryable (429, 5xx, timeout) vs non-retryable (4xx, malformed JSON)

---

## 4. Performance & Monitoring

- **4.1** Process all data within 60 seconds
- **4.2** Track success/failure rates and processing times
- **4.3** Memory-efficient processing (bounded queue, don't load all data at once)

---

## 5. Testing

- **5.1** Unit tests for key components
- **5.2** Integration test for full pipeline
- **5.3** Error scenario tests (network failures, malformed data)
- **5.4** Minimum 80% code coverage

---

## 6. Documentation

- **6.1** README with setup and run instructions
- **6.2** Code comments explaining concurrency decisions
- **6.3** Architecture overview
- **6.4** AI_USAGE.md documenting AI tool usage

---
