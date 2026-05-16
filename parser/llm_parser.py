import os
import json
import logging
import google.generativeai as genai
from groq import Groq
from pydantic import ValidationError

from .models import APISchema

logger = logging.getLogger("smart_api_tool")

SYSTEM_PROMPT = """
You are an expert API integration engineer. Extract the API specification
from the provided documentation text and return it as a structured JSON object.

CRITICAL INSTRUCTION: Carefully read the text to find ALL API resources or routes mentioned (e.g., /posts, /users, /comments, etc). Even if the documentation only briefly lists a route, you MUST infer the standard REST CRUD endpoints for it. For example, if you see '/users', assume there is a 'GET /users' and 'GET /users/{id}'. Do not leave out any routes mentioned on the page.

Your output MUST strictly match this exact JSON structure:
{
    "title": "API Name",
    "base_url": "https://api.example.com",
    "version": "1.0",
    "auth": {
        "type": "bearer",  # or "api_key" or "none"
        "header_name": "Authorization"
    },
    "endpoints": [
        {
            "path": "/users",
            "method": "GET",  # Must be GET, POST, PUT, DELETE, or PATCH
            "summary": "Description of what it does",
            "parameters": [
                {
                    "name": "id",
                    "type": "string",
                    "required": true,
                    "description": "User ID",
                    "location": "path"  # query, path, header, body
                }
            ],
            "response_description": "Returns user object"
        }
    ],
    "extraction_notes": ["Explicitly document ANY assumptions or inferred endpoints here"]
}

--- FEW-SHOT EXAMPLE ---
BAD INPUT TEXT:
"Our API has /users, /posts, and /comments."

EXPECTED OUTPUT LOGIC:
Even though the text doesn't explicitly say "GET /users", you MUST infer standard CRUD endpoints.
You should generate: GET /users, POST /users, GET /posts, POST /posts, GET /comments, etc.
Any endpoints you infer that were not explicitly detailed MUST be logged in 'extraction_notes'.
------------------------

Return ONLY valid JSON. Do not include markdown formatting like ```json
or any other text before or after the JSON.
"""

STRICT_PROMPT = """
Previous attempt failed to parse as valid JSON matching the schema.
You MUST return ONLY valid JSON matching the schema. NO Markdown formatting,
NO comments, NO extra text.
"""


def _call_llm(prompt: str, text: str) -> str:
    """Helper to try Gemini first, then fallback to Groq."""
    gemini_key = os.environ.get("GEMINI_API_KEY")
    if gemini_key:
        try:
            genai.configure(api_key=gemini_key)
            model = genai.GenerativeModel(
                'gemini-2.5-flash',
                generation_config=genai.types.GenerationConfig(temperature=0.0)
            )
            full_prompt = (
                f"System Instructions:\n{prompt}\n\n"
                f"User Input (Documentation):\n{text}"
            )
            response = model.generate_content(full_prompt)
            return response.text
        except Exception as e:
            logger.warning(
                f"Gemini API call failed: {e}. Falling back to Groq."
            )

    groq_key = os.environ.get("GROQ_API_KEY")
    if groq_key:
        try:
            client = Groq(api_key=groq_key)
            completion = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": text}
                ],
                temperature=0.0
            )
            return completion.choices[0].message.content or ""
        except Exception as e:
            logger.error(f"Groq API call failed: {e}")
            raise RuntimeError(
                "Both primary (Gemini) and fallback (Groq) LLMs failed."
            )

    raise RuntimeError(
        "No LLM API keys found. Please set GEMINI_API_KEY or GROQ_API_KEY."
    )


def _clean_json_string(raw: str) -> str:
    """Strip markdown code blocks if the LLM ignores instructions."""
    raw = raw.strip()
    if raw.startswith("```json"):
        raw = raw[7:]
    elif raw.startswith("```"):
        raw = raw[3:]
    if raw.endswith("```"):
        raw = raw[:-3]
    return raw.strip()


def compute_confidence(schema: APISchema, raw_text: str) -> float:
    """Compute a strict confidence score mathematically penalizing ambiguity."""
    score = 1.0
    if not schema.endpoints:
        return 0.1

    if not schema.base_url or schema.base_url == "https://api.example.com":
        score -= 0.2

    if schema.auth.type == "none" and "auth" in raw_text.lower():
        score -= 0.1

    # Penalize endpoints with missing details (Ambiguity Heuristic)
    ambiguous_endpoints = 0
    for ep in schema.endpoints:
        if not ep.summary or ep.summary == "Description of what it does":
            ambiguous_endpoints += 1
        # If path has {id} but no parameters were extracted
        if "{" in ep.path and "}" in ep.path and not ep.parameters:
            score -= 0.1
        # Penalize overly generic Optional[Any] types
        for param in ep.parameters:
            if param.type == "Any":
                score -= 0.05

    if ambiguous_endpoints > 0:
        score -= (0.1 * ambiguous_endpoints)

    return max(0.1, round(score, 2))


# High-signal API patterns — keep these paragraphs together in chunks
_API_SIGNALS = (
    "GET ", "POST ", "PUT ", "DELETE ", "PATCH ",
    "/api", "endpoint", "parameter", "auth",
    "bearer", "response",
)


def chunk_api_docs(text: str, max_chars: int = 7000) -> list:
    """Split long API documentation into domain-aware chunks.

    Splits on blank lines (paragraph boundaries) so API-relevant blocks
    (HTTP methods, paths, auth, parameters) are kept together within a chunk
    rather than cut mid-context. Chunks never exceed max_chars characters.
    """
    paragraphs = text.split("\n\n")
    chunks = []
    current: list = []
    current_len = 0

    for para in paragraphs:
        is_api_relevant = any(sig in para for sig in _API_SIGNALS)
        para_len = len(para) + 2  # +2 for the \n\n separator

        # If adding this paragraph would exceed the limit, flush the current chunk
        if current_len + para_len > max_chars and current:
            # But if this paragraph is API-relevant and the chunk is small,
            # keep it together to avoid losing context
            if is_api_relevant and current_len < max_chars * 0.5:
                current.append(para)
                current_len += para_len
                continue
            chunks.append("\n\n".join(current))
            current = []
            current_len = 0

        current.append(para)
        current_len += para_len

    if current:
        chunks.append("\n\n".join(current))

    return chunks


def parse_api_docs(text: str) -> APISchema:
    """Extract APISchema from documentation text using LLMs.

    For short docs (<= 7000 chars): single LLM call.
    For long docs (> 7000 chars): splits into domain-aware chunks,
    calls the LLM per chunk, then merges and deduplicates endpoints.
    Policy: if a chunk fails, log the error and continue with others.
    """
    logger.info("Starting LLM parsing of API documentation")

    if len(text) > 7000:
        chunks = chunk_api_docs(text)
        logger.info(
            "Long API doc detected: split into %d chunks for LLM parsing",
            len(chunks),
        )
        return _parse_chunked(text, chunks)

    return _parse_single(text)


def _parse_single(text: str) -> APISchema:
    """Single LLM call for short documents."""
    raw_response = _call_llm(SYSTEM_PROMPT, text)

    try:
        clean_text = _clean_json_string(raw_response)
        data = json.loads(clean_text)
        schema = APISchema(**data)
        schema.confidence_score = compute_confidence(schema, text)

        if schema.confidence_score < 0.6:
            raise ValueError(
                f"Confidence too low ({schema.confidence_score}). "
                "Triggering fallback."
            )

        logger.info(f"Parsed docs with confidence {schema.confidence_score}")
        return schema

    except (json.JSONDecodeError, ValidationError) as e:
        logger.error(f"Initial parse failed: {e}. Retrying.")
        retry_prompt = f"{SYSTEM_PROMPT}\n{STRICT_PROMPT}"
        raw_retry = _call_llm(retry_prompt, text)

        try:
            clean_retry = _clean_json_string(raw_retry)
            data_retry = json.loads(clean_retry)
            schema = APISchema(**data_retry)
            schema.confidence_score = compute_confidence(schema, text)
            logger.info(
                f"Retry succeeded with confidence {schema.confidence_score}"
            )
            return schema

        except Exception as retry_e:
            logger.error(f"Retry also failed: {retry_e}. Building partial.")
            return APISchema(
                title="Unknown API",
                base_url="",
                endpoints=[],
                confidence_score=0.1,
                extraction_notes=[
                    "Extraction failed completely.",
                    str(retry_e),
                ],
            )


def _parse_chunked(original_text: str, chunks: list) -> APISchema:
    """Parse each chunk independently and merge results.

    Policy: errors on individual chunks are logged and skipped so a single
    bad chunk cannot block extraction from the rest of the document.
    """
    schemas = []
    for i, chunk in enumerate(chunks):
        try:
            logger.info("Parsing chunk %d/%d", i + 1, len(chunks))
            schema = _parse_single(chunk)
            schemas.append(schema)
        except Exception as exc:
            logger.warning(
                "Chunk %d/%d failed: %s \u2014 skipping.", i + 1, len(chunks), exc
            )

    if not schemas:
        return APISchema(
            title="Unknown API",
            base_url="",
            endpoints=[],
            confidence_score=0.1,
            extraction_notes=["All chunks failed during LLM parsing."],
        )

    # Use title/base_url/auth from the first successful schema
    merged = schemas[0]

    # Merge and deduplicate endpoints across all chunk schemas
    seen = {(ep.path, ep.method) for ep in merged.endpoints}
    for schema in schemas[1:]:
        for ep in schema.endpoints:
            key = (ep.path, ep.method)
            if key not in seen:
                seen.add(key)
                merged.endpoints.append(ep)

    # Confidence = average of per-chunk scores (explicit heuristic)
    merged.confidence_score = round(
        sum(s.confidence_score for s in schemas) / len(schemas), 2
    )
    merged.extraction_notes.append(
        f"Parsed from {len(chunks)} chunks; {len(schemas)} succeeded."
    )

    logger.info(
        "Merged %d chunks into %d unique endpoints (confidence: %s)",
        len(schemas),
        len(merged.endpoints),
        merged.confidence_score,
    )
    return merged
