import asyncio
import logging
from typing import Any, Dict, List

from generator.codegen import generate_sdk
from parser.llm_parser import parse_api_docs
from scraper.scraper import scrape

logger = logging.getLogger("smart_api_tool")


async def process_url(
    url: str, semaphore: asyncio.Semaphore
) -> Dict[str, Any]:
    loop = asyncio.get_event_loop()

    async with semaphore:
        logger.info(f"[ASYNC] Starting: {url}")
        try:
            from functools import partial

            text = await loop.run_in_executor(None, partial(scrape, url))
            schema = await loop.run_in_executor(
                None, partial(parse_api_docs, text)
            )
            sdk_path = await loop.run_in_executor(
                None, partial(generate_sdk, schema)
            )

            logger.info(f"[ASYNC] Done: {url} -> {sdk_path}")
            return {
                "url": url,
                "status": "success",
                "output": sdk_path,
                "endpoints": len(schema.endpoints),
                "confidence": schema.confidence_score,
            }
        except Exception as exc:
            logger.error(f"[ASYNC] Failed: {url} - {exc}")
            return {
                "url": url,
                "status": "error",
                "error": str(exc),
            }


async def process_batch(
    urls: List[str], max_concurrent: int = 3
) -> List[Dict[str, Any]]:
    semaphore = asyncio.Semaphore(max_concurrent)
    tasks = [process_url(url, semaphore) for url in urls]
    results = await asyncio.gather(*tasks)
    return list(results)
