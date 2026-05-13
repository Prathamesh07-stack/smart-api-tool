# Smart API Tool – SDK Generator

> A tool that takes an API docs URL or OpenAPI spec and generates a ready-to-use Python SDK automatically.

## What It Does

1. **Scrapes** API documentation from any public URL (handles static HTML, JS-rendered pages, and multi-page docs)
2. **Understands** the API using an LLM (Gemini primary, Groq fallback) and validates the extracted schema with Pydantic
3. **Generates** a clean, importable Python SDK using Jinja2 templates

## Quick Start

```bash
# 1. Clone & set up environment
git clone <repo-url>
cd smart-api-tool

python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r requirements.txt
playwright install chromium       # for JS-rendered docs

# 2. Add your API keys
cp .env.example .env
# Edit .env → add GEMINI_API_KEY and/or GROQ_API_KEY

# 3. Run
python main.py --url https://jsonplaceholder.typicode.com/
python main.py --spec path/to/swagger.yaml
python main.py --urls url1 url2 url3   # batch mode
```

## Project Structure

```
smart-api-tool/
├── main.py                  # CLI entry point
├── config.yaml              # Default configuration
├── requirements.txt
├── .env.example
├── scraper/                 # Web scraping + robots.txt compliance
├── parser/                  # LLM extraction + Pydantic validation
├── generator/               # Jinja2 SDK templates + codegen
├── evaluation/              # Metrics, quality checks, smoke tests
├── utils/                   # Logger and shared utilities
├── tests/                   # Unit + integration tests
├── output/                  # Generated SDK files (git-ignored)
└── logs/                    # Runtime logs (git-ignored)
```

## Configuration

Edit `config.yaml` to change LLM model, output directory, scraping timeouts, and concurrency limits.

---

> **Note:** Detailed documentation is work in progress. See `docs/design.md` (coming in later issues).
