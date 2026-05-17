import argparse
import asyncio
import logging
import os
import sys
from urllib.parse import urlparse

from dotenv import load_dotenv

from async_pipeline import process_batch
from evaluation.metrics import (
    LatencyTracker,
    check_code_quality,
    compute_extraction_accuracy,
)
from evaluation.smoke_test import smoke_test_sdk
from generator.codegen import format_method_name, generate_sdk
from parser.graphql_parser import parse_graphql_url
from parser.llm_parser import parse_api_docs
from parser.models import APISchema
from parser.openapi_parser import parse_openapi_file
from scraper.scraper import scrape
from utils.logger import setup_logger


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smart API Tool Orchestrator")
    parser.add_argument("--url", type=str, help="Single URL to scrape and parse")
    parser.add_argument(
        "--urls",
        type=str,
        nargs="+",
        help="One or more URLs for batch processing",
    )
    parser.add_argument("--spec", type=str, help="Path to OpenAPI YAML/JSON file")

    parser.add_argument(
        "--playwright", action="store_true", help="Use Playwright for scraping"
    )
    parser.add_argument(
        "--follow-links", action="store_true", help="Follow pagination links"
    )
    parser.add_argument(
        "--evaluate",
        action="store_true",
        help="Run extraction evaluation against ground truth",
    )
    parser.add_argument(
        "--smoke-test",
        action="store_true",
        help="Run dynamic smoke tests against generated SDK",
    )

    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Review and refine extracted API schema before generating SDK",
    )

    parser.add_argument(
        "--graphql",
        action="store_true",
        help="Treat --url as a GraphQL endpoint and parse via introspection",
    )
    parser.add_argument(
        "--graphql-key",
        default="",
        help="API key for authenticated GraphQL endpoints (sent as Bearer token)",
    )

    parser.add_argument(
        "--lang",
        type=str,
        default="python",
        choices=["python", "javascript"],
        help="Target SDK language: python (default) or javascript",
    )

    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        help="Logging level (e.g. INFO, DEBUG)",
    )
    parser.add_argument("--log-file", type=str, help="Optional file to write logs to")

    return parser.parse_args()


def interactive_refinement(schema: APISchema) -> APISchema:
    def _prompt_or_default(prompt: str) -> str:
        try:
            return input(prompt)
        except (KeyboardInterrupt, EOFError):
            # In non-interactive environments (e.g. Colab), treat prompt failures
            # the same as pressing ENTER to keep defaults.
            return ""

    print(f'\nExtracted {len(schema.endpoints)} endpoints from "{schema.title}"')
    print(f"Confidence score: {schema.confidence_score}")
    if schema.confidence_score < 0.7:
        print("WARNING: Low confidence extraction. Please review endpoints carefully.")

    print("\n--- Endpoints ---")
    for i, ep in enumerate(schema.endpoints):
        print(f"[{i+1}] {ep.method} {ep.path} — {ep.summary}")

    print()
    endpoints_input = _prompt_or_default(
        "Press ENTER to accept all endpoints,\nor type endpoint numbers to remove (e.g. 1,3,5): "
    )

    if endpoints_input.strip():
        try:
            to_remove = [
                int(x.strip()) for x in endpoints_input.split(",") if x.strip()
            ]
            new_endpoints = [
                ep for i, ep in enumerate(schema.endpoints) if (i + 1) not in to_remove
            ]
            schema.endpoints = new_endpoints
        except ValueError:
            print("Invalid input, keeping all endpoints.")

    print()
    base_url_input = _prompt_or_default(
        f"Edit base URL? Current: {schema.base_url}\nNew value (ENTER to keep): "
    )

    if base_url_input.strip():
        schema.base_url = base_url_input.strip()

    print()
    auth_input = _prompt_or_default(
        f"Auth type detected: {schema.auth.type}\nChange? (bearer/api_key/none, ENTER to keep): "
    )

    auth_input = auth_input.strip().lower()
    if auth_input in ("bearer", "api_key", "none"):
        schema.auth.type = auth_input
        if auth_input == "bearer":
            schema.auth.header_name = "Authorization"
        elif auth_input == "api_key":
            header_input = _prompt_or_default("Enter header name for API key: ")
            if header_input.strip():
                schema.auth.header_name = header_input.strip()

    print(
        f'\nProceeding with {len(schema.endpoints)} endpoints from "{schema.title}" (base URL: {schema.base_url}, auth: {schema.auth.type})\n'
    )
    return schema


def run_single(args: argparse.Namespace) -> None:
    logger = logging.getLogger("smart_api_tool")
    tracker = LatencyTracker()

    if args.graphql:
        logger.info("Mode: GraphQL introspection")
        tracker.start("graphql_parse")
        schema = parse_graphql_url(args.url, api_key=args.graphql_key)
        tracker.stop("graphql_parse")

        if args.interactive:
            try:
                schema = interactive_refinement(schema)
            except (KeyboardInterrupt, EOFError):
                logger.warning(
                    "Interactive prompts interrupted; proceeding with extracted defaults."
                )

        tracker.start("codegen")
        sdk_path = generate_sdk(schema, language=args.lang)
        tracker.stop("codegen")
        logger.info(f"Latency Report: {tracker.report()}")
        cq_result = check_code_quality(sdk_path)
        logger.info(
            f"Code Quality: {cq_result['status']} "
            f"({cq_result['issue_count']} issues)"
        )
        return

    tracker.start("scrape")
    text = scrape(
        args.url, use_playwright=args.playwright, follow_links=args.follow_links
    )
    tracker.stop("scrape")

    tracker.start("llm_parse")
    schema = parse_api_docs(text)
    tracker.stop("llm_parse")

    if args.interactive:
        try:
            schema = interactive_refinement(schema)
        except (KeyboardInterrupt, EOFError):
            logger.warning(
                "Interactive prompts interrupted; proceeding with extracted defaults."
            )

    tracker.start("codegen")
    sdk_path = generate_sdk(schema, language=args.lang)
    tracker.stop("codegen")

    stage_times = tracker.report()
    logger.info(f"Latency Report: {stage_times}")

    cq_result = check_code_quality(sdk_path)
    logger.info(
        f"Code Quality: {cq_result['status']} " f"({cq_result['issue_count']} issues)"
    )

    if args.evaluate:
        domain = urlparse(args.url).netloc.split(".")[0]
        gt_path = f"tests/ground_truth/{domain}.yaml"
        if os.path.exists(gt_path):
            metrics = compute_extraction_accuracy(schema, gt_path)
            logger.info(f"Evaluation Metrics: {metrics}")
        else:
            logger.info(
                f"No ground truth file found for '{domain}', " "skipping evaluation."
            )

    if args.smoke_test:
        # Autonomously discover safe GET endpoints with no required params
        safe_calls = []
        for ep in schema.endpoints:
            if ep.method == "GET" and not any(p.required for p in ep.parameters):
                method_name = format_method_name(ep.method, ep.path)
                safe_calls.append((method_name, {}))
            if len(safe_calls) >= 2:
                break
        if safe_calls:
            smoke_result = smoke_test_sdk(sdk_path, safe_calls)
            logger.info(f"Smoke Test Summary: {smoke_result}")
        else:
            logger.info("No safe GET endpoints found for smoke testing, skipping.")


def run_batch(args: argparse.Namespace) -> None:
    logger = logging.getLogger("smart_api_tool")
    logger.info(f"Starting batch processing of {len(args.urls)} URLs")
    results = asyncio.run(process_batch(args.urls))

    for res in results:
        logger.info(
            f"Batch Result: {res['url']} -> {res['status']} | "
            f"Output: {res.get('output', res.get('error'))}"
        )


def run_spec(args: argparse.Namespace) -> None:
    logger = logging.getLogger("smart_api_tool")
    schema = parse_openapi_file(args.spec)
    sdk_path = generate_sdk(schema, language=args.lang)

    logger.info(
        f"Parsed OpenAPI Spec: {schema.title} " f"({len(schema.endpoints)} endpoints)"
    )
    logger.info(f"Generated SDK path: {sdk_path}")

    cq_result = check_code_quality(sdk_path)
    logger.info(
        f"Code Quality Check: {cq_result['status']} "
        f"({cq_result['issue_count']} issues)"
    )


def main() -> None:
    load_dotenv()
    args = parse_args()
    logger = setup_logger(
        "smart_api_tool", level=args.log_level, log_file=args.log_file
    )

    if args.urls:
        run_batch(args)
    elif args.url:
        run_single(args)
    elif args.spec:
        run_spec(args)
    else:
        logger.error(
            "Missing required input. " "Must provide --url, --urls, or --spec."
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
