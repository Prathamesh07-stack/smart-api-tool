# Smart API Tool Design Document

## Problem Statement
Developers spend countless hours manually writing API integration code, models, and boilerplate SDKs by reading lengthy API documentation. While OpenAPI specifications exist, many enterprise APIs only offer static documentation pages. The **Smart API Tool** solves this by autonomously crawling any API documentation URL, interpreting the complex endpoints using Large Language Models (LLMs), and dynamically generating a production-ready, perfectly formatted Python SDK in seconds.

## Architecture

![Architecture Diagram](../Architecture%20Diagram.png)

## Key Decisions

### 1. LLM + Pydantic Gate vs. Pure LLM Generation
Relying entirely on an LLM to generate raw python files natively introduces massive non-determinism, syntax hallucination, and unpredictable outputs. 
**The Solution**: We utilize the LLM strictly as a "Data Extraction Engine". The LLM is forced via Few-Shot prompting to output pure JSON. This JSON is immediately intercepted by a strict `Pydantic` validation gate (`APISchema`). If the LLM hallucinates an invalid HTTP method or misses required fields, Pydantic catches it natively, allowing us to implement mathematical fallback heuristics.

### 2. The 3-Tier Scraper Architecture
Not all documentation sites are built equally.
*   **Tier 1 (Robots.txt):** The scraper always acts as a polite internet citizen, refusing to scrape sites that explicitly forbid it, preventing IP bans.
*   **Tier 2 (Static):** For fast, standard HTML pages, we use `requests` and `markdownify` to instantly extract context-preserved markdown.
*   **Tier 3 (Dynamic Playwright):** Modern sites (like Stripe or GitHub) render docs dynamically via JavaScript. The architecture spins up a headless Chromium browser (`Playwright`) to wait for network idle before extracting the DOM.

### 3. Jinja2 Templating
Because the LLM is restricted to pure JSON extraction, the actual Python Code Generation is handled by `Jinja2`. This guarantees that the generated SDK is structurally deterministic, syntactically flawless, and safe to execute.

### 4. Asynchronous Batch Pipeline
Enterprise users need to process dozens of APIs at once. We implemented `asyncio.gather` coupled with a concurrency `Semaphore`. This allows the CLI to fire off multiple headless browsers and LLM network requests simultaneously, drastically reducing total execution latency while respecting rate-limits.

## Evaluation Design
To prove the tool is production-ready, we built a comprehensive, automated evaluation suite (`metrics.py`):
1.  **Precision/Recall/F1**: The system compares the LLM's dynamically extracted endpoints against a hardcoded YAML ground-truth file. It mathematically calculates the F1 score, heavily penalizing hallucinations.
2.  **Latency Tracking**: Every stage (Scraping, Parsing, Codegen) is benchmarked to identify bottlenecks.
3.  **Flake8 Code Quality**: The `codegen.py` engine utilizes `autoflake` and `black` to automatically format the SDK. A `flake8` subprocess then verifies the code contains 0 syntax or style issues.
4.  **Live Smoke Tests**: The system dynamically imports the generated SDK in-memory and fires real HTTP requests to the live API, proving the SDK actually functions.

## Challenges and Fixes
*   **Context Loss**: Initially, `BeautifulSoup` stripped HTML tables, destroying parameter context for the LLM. We fixed this by integrating `markdownify`, preserving markdown tables.
*   **LLM Ambiguity**: The LLM struggled to infer CRUD methods from vague docs. We fixed this by hardcoding `temperature=0.0` and rewriting the System Prompt to include strict Few-Shot Learning examples.
*   **Code Linting Fails**: Jinja2 templates often imported unused modules (like `typing.Dict`). We integrated `autoflake` into the generator pipeline to physically rip out unused imports before saving the file.

## Potential V2 Improvements
1.  **Multi-Language Support**: Expanding the `Jinja2` engine to support generating TypeScript, Go, and Rust SDKs.
2.  **Advanced Authentication**: Implementing complex OAuth2 handshakes dynamically within the generated Client class.
3.  **Dynamic Crawling**: Expanding the scraper to automatically follow pagination links ("Next Page") to compile massive API documentation spanning multiple URLs.
4.  **Multi-Language UI / CLI**: The interactive CLI and any UI layer are architected so they can be implemented in languages and runtimes beyond Python and JavaScript (for example, a TypeScript/React web UI, a Rust CLI, or a small Go wrapper). The generator and templates can be extended to emit language-specific templates and wiring to support those interfaces.

## Tokenization & Embedding Strategy

### Scope Decision
A full embedding/RAG pipeline with a vector database is out of scope for a 6-day prototype. Most real-world API documentation pages fit comfortably within modern LLM context windows (Gemini 2.5 Flash supports 1M tokens). For the remaining edge cases — extremely long paginated documentation — we use a **domain-aware chunking strategy** instead of naive hard truncation.

### Domain-Specific Chunking (Implemented)
`chunk_api_docs()` in `parser/llm_parser.py` implements a paragraph-based splitter with API-domain awareness:

- Splits the scraped text on blank lines (`\n\n`) to preserve paragraph boundaries.
- Builds chunks up to a `max_chars` limit (default: 7,000 characters).
- Treats paragraphs containing high-signal API keywords (`GET`, `POST`, `/api`, `endpoint`, `auth`, `bearer`, `response`, `parameter`) as **priority paragraphs** — if the current chunk is under 50% capacity, these paragraphs are kept with the preceding context rather than flushed to a new chunk.

This is "domain-specific" because generic prose chunkers (e.g. sentence splitters) would naively break an HTTP endpoint definition mid-way. By recognising API vocabulary, our chunker keeps semantically related lines together, giving the LLM better context per call.

When a long document is detected, `parse_api_docs()` calls `_parse_chunked()` which:
1. Sends each chunk to the LLM independently.
2. Merges all returned `APISchema` objects.
3. Deduplicates endpoints by `(path, method)` key.
4. Computes the final `confidence_score` as the **average** of all per-chunk scores.

### Future Embedding-Based Improvement
For V2, a richer retrieval strategy could be added:
1. Embed each paragraph using a lightweight model (e.g. `text-embedding-3-small` or `nomic-embed-text`).
2. At parse time, compute cosine similarity between a fixed query ("API endpoints, HTTP methods, authentication, parameters") and all paragraph embeddings.
3. Select only the top-K most relevant paragraphs before LLM extraction — replacing or augmenting `chunk_api_docs`.
4. Optionally store embeddings in a lightweight vector store (e.g. ChromaDB) for repeated queries against the same documentation.

### Confidence Score as Quality Proxy
`APISchema.confidence_score` acts as a coarse extraction quality signal across chunks:
- `1.0` = all endpoints have summaries, base URL is resolved, auth is detected.
- Deducted for: missing base URL (`-0.2`), missing auth when "auth" appears in text (`-0.1`), ambiguous endpoint summaries (`-0.1` per endpoint), path parameters without corresponding `parameters` entries (`-0.1`).
- In chunked mode, the final score is the **mean** of per-chunk scores, reflecting overall extraction quality across the full document.
