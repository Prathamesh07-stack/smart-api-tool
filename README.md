# Smart API Tool – Auto-generated Python SDK from API docs

Smart API Tool is an autonomous, production-ready pipeline that dynamically converts static REST API documentation into fully functioning, PEP-8 compliant Python SDKs using LLM parsing, Pydantic validation, and deterministic Jinja2 code generation.

## Architecture

![Architecture Diagram](Architecture%20Diagram.png)

The tool processes documentation through a 5-tier pipeline:
1. **Scraping**: Fetches static HTML or renders JavaScript-heavy sites via Playwright, respecting `robots.txt`.
2. **LLM Parsing**: Gemini/Groq extracts API endpoints, HTTP methods, and parameters using strict Few-Shot prompts.
3. **Validation**: Pydantic strictly enforces the `APISchema` structure, eliminating hallucinations.
4. **Code Generation**: A deterministic Jinja2 template maps the schema into a robust Python class.
5. **Quality Assurance**: `autoflake` and `black` auto-format the code, ensuring 0 Code Quality issues.

## Setup

```bash
git clone https://github.com/Prathamesh07-stack/smart-api-tool.git
cd smart-api-tool

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

*(Ensure you have your `.env` file populated with `GEMINI_API_KEY` and `GROQ_API_KEY`)*

Create a `.env` file at the project root with your API keys before running the tool. Example:

```bash
# .env example
GEMINI_API_KEY=your_gemini_key_here
GROQ_API_KEY=your_groq_key_here
```

## Running the tool locally (ordered flow)

Follow this exact flow when running locally from the repo root. Replace API keys where noted.

1) Run the test suite first

```bash
# Create + activate virtualenv (macOS / Linux)
python -m venv .venv
source .venv/bin/activate

# Install deps and Playwright
pip install -r requirements.txt
playwright install chromium
playwright install-deps

# Run tests
PYTHONPATH=. pytest tests/ -v
```

2) Main URL checks

Python (generate Python SDK):

```bash
# Main URL check with Python as target SDK language
python main.py \
  --url https://jsonplaceholder.typicode.com/ \
  --interactive \
  --lang python \
  --log-level INFO
```

JavaScript (generate JS SDK):

```bash
# Main URL check with JavaScript as target SDK language
python main.py \
  --url https://jsonplaceholder.typicode.com/ \
  --interactive \
  --lang javascript \
  --log-level INFO
```

3) GraphQL URL checks

Python (GraphQL introspection):

```bash
# GraphQL URL check with Python as target SDK language
python main.py \
  --url https://countries.trevorblades.com/ \
  --graphql \
  --lang python \
  --log-level INFO
```

JavaScript (GraphQL introspection):

```bash
# GraphQL URL check with JavaScript as target SDK language
python main.py \
  --url https://countries.trevorblades.com/ \
  --graphql \
  --lang javascript \
  --log-level INFO
```

4) Local OpenAPI / YAML spec parsing

Python (spec -> Python SDK):

```bash
# YAML/OpenAPI parser check with Python as target SDK language
curl -sL https://raw.githubusercontent.com/swagger-api/swagger-petstore/master/src/main/resources/openapi.yaml \
  -o tests/real_petstore_openapi.yaml

python main.py \
  --spec tests/real_petstore_openapi.yaml \
  --lang python \
  --log-level INFO
```

JavaScript (spec -> JS SDK):

```bash
# YAML/OpenAPI parser check with JavaScript as target SDK language
curl -sL https://raw.githubusercontent.com/swagger-api/swagger-petstore/master/src/main/resources/openapi.yaml \
  -o tests/real_petstore_openapi.yaml

python main.py \
  --spec tests/real_petstore_openapi.yaml \
  --lang javascript \
  --log-level INFO
```

5) Async / batch processing (use the provided URLs)

```bash
# Async batch URL check with Playwright
python main.py \
  --urls https://docs.github.com/en/rest/users/users https://docs.stripe.com/api/customers \
  --playwright \
  --log-level INFO
```

6) robots.txt denial check (legality check)

```bash
# robots.txt legality check for crawl allowance/disallowance
python main.py \
  --url https://reqres.in/ \
  --log-level INFO
```

Expected: if the site disallows crawling the given path the run will log a robots.txt warning and the scraper will raise a `PermissionError` (the pipeline halts).

---

## Running in Google Colab (ordered flow)

Paste each block below into its own Colab cell. Replace API keys where noted.

1) Clone and install

```python
!git clone https://github.com/Prathamesh07-stack/smart-api-tool.git
%cd smart-api-tool
!pip install -r requirements.txt
!playwright install chromium
!playwright install-deps
```

2) Run tests

```python
!PYTHONPATH=. pytest tests/ -v
```


3) Set LLM keys once for Colab runtime

Run this once after tests. Subsequent `!python` shell commands in the same runtime will inherit these variables.

```python
import os

os.environ['GEMINI_API_KEY'] = 'paste_your_gemini_key_here'
os.environ['GROQ_API_KEY'] = 'paste_your_groq_key_here'

print('GEMINI_API_KEY loaded:', bool(os.environ.get('GEMINI_API_KEY')))
```

4) Main URL checks (Python)

```python
# Main URL check with Python as target SDK language
!python main.py \
  --url https://jsonplaceholder.typicode.com/ \
  --interactive \
  --lang python \
  --log-level INFO
```

Main URL checks (JavaScript)

```python
# Main URL check with JavaScript as target SDK language
!python main.py \
  --url https://jsonplaceholder.typicode.com/ \
  --interactive \
  --lang javascript \
  --log-level INFO
```

5) GraphQL checks (Python)

```python
# GraphQL URL check with Python as target SDK language
!python main.py \
  --url https://countries.trevorblades.com/ \
  --graphql \
  --lang python \
  --log-level INFO
```

GraphQL checks (JavaScript)

```python
# GraphQL URL check with JavaScript as target SDK language
!python main.py \
  --url https://countries.trevorblades.com/ \
  --graphql \
  --lang javascript \
  --log-level INFO
```

6) YAML / OpenAPI spec (Python)

```python
# YAML/OpenAPI parser check with Python as target SDK language
!curl -sL https://raw.githubusercontent.com/swagger-api/swagger-petstore/master/src/main/resources/openapi.yaml \
  -o tests/real_petstore_openapi.yaml
!python main.py \
  --spec tests/real_petstore_openapi.yaml \
  --lang python \
  --log-level INFO
```

YAML / OpenAPI spec (JavaScript)

```python
# YAML/OpenAPI parser check with JavaScript as target SDK language
!curl -sL https://raw.githubusercontent.com/swagger-api/swagger-petstore/master/src/main/resources/openapi.yaml \
  -o tests/real_petstore_openapi.yaml
!python main.py \
  --spec tests/real_petstore_openapi.yaml \
  --lang javascript \
  --log-level INFO
```

7) Async / batch (Colab)

```python
# Async batch URL check with Playwright
!python main.py \
  --urls https://docs.github.com/en/rest/users/users https://docs.stripe.com/api/customers \
  --playwright \
  --log-level INFO
```

8) robots.txt denial check (Colab)

```python
# robots.txt legality check for crawl allowance/disallowance
!python main.py \
  --url https://reqres.in/ \
  --log-level INFO
```

---


