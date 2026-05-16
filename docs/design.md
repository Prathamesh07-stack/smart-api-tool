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
