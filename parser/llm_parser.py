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
    "extraction_notes": ["Any assumptions made"]
}

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
            model = genai.GenerativeModel('gemini-2.5-flash')
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
                temperature=0.1
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
    """Compute a simple confidence score heuristically."""
    score = 1.0
    if not schema.endpoints:
        score -= 0.5
    if not schema.base_url or schema.base_url == "https://api.example.com":
        score -= 0.2
    if schema.auth.type == "none" and "auth" in raw_text.lower():
        score -= 0.1
    return max(0.1, round(score, 2))


def parse_api_docs(text: str) -> APISchema:
    """Extract APISchema from documentation text using LLMs."""
    logger.info("Starting LLM parsing of API documentation")
    raw_response = _call_llm(SYSTEM_PROMPT, text)

    try:
        clean_text = _clean_json_string(raw_response)
        data = json.loads(clean_text)
        schema = APISchema(**data)
        schema.confidence_score = compute_confidence(schema, text)
        logger.info(
            f"Parsed docs with confidence {schema.confidence_score}"
        )
        return schema

    except (json.JSONDecodeError, ValidationError) as e:
        logger.error(f"Initial parse failed: {e}. Retrying.")

        # Retry once with stricter instructions
        retry_prompt = f"{SYSTEM_PROMPT}\n{STRICT_PROMPT}"
        raw_response_retry = _call_llm(retry_prompt, text)

        try:
            clean_text_retry = _clean_json_string(raw_response_retry)
            data_retry = json.loads(clean_text_retry)
            schema = APISchema(**data_retry)
            schema.confidence_score = compute_confidence(schema, text)
            logger.info(
                f"Retry succeeded with confidence {schema.confidence_score}"
            )
            return schema

        except Exception as retry_e:
            logger.error(f"Retry also failed: {retry_e}. Building partial.")
            # Option 2 from spec: Build a partial schema with 0.1 confidence
            return APISchema(
                title="Unknown API",
                base_url="",
                endpoints=[],
                confidence_score=0.1,
                extraction_notes=[
                    "Extraction failed completely.",
                    str(retry_e)
                ]
            )
