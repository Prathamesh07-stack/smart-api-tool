import argparse
import asyncio
import logging
import sys

from async_pipeline import process_batch
from evaluation.metrics import (
    LatencyTracker,
    check_code_quality,
    compute_extraction_accuracy,
)
from evaluation.smoke_test import smoke_test_sdk
from generator.codegen import generate_sdk
from parser.llm_parser import parse_api_docs
from parser.openapi_parser import parse_openapi_file
from scraper.scraper import scrape
from utils.logger import setup_logger


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smart API Tool Orchestrator")
    parser.add_argument(
        "--url", type=str, help="Single URL to scrape and parse"
    )
    parser.add_argument(
        "--urls",
        type=str,
        nargs="+",
        help="One or more URLs for batch processing",
    )
    parser.add_argument(
        "--spec", type=str, help="Path to OpenAPI YAML/JSON file"
    )

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
        "--log-level",
        type=str,
        default="INFO",
        help="Logging level (e.g. INFO, DEBUG)",
    )
    parser.add_argument(
        "--log-file", type=str, help="Optional file to write logs to"
    )

    return parser.parse_args()


def run_single(args: argparse.Namespace) -> None:
    logger = logging.getLogger("smart_api_tool")
    tracker = LatencyTracker()

    tracker.start("scrape")
    text = scrape(
        args.url, use_playwright=args.playwright, follow_links=args.follow_links
    )
    tracker.stop("scrape")

    tracker.start("llm_parse")
    schema = parse_api_docs(text)
    tracker.stop("llm_parse")

    tracker.start("codegen")
    sdk_path = generate_sdk(schema)
    tracker.stop("codegen")

    stage_times = tracker.report()
    logger.info(f"Latency Report: {stage_times}")

    cq_result = check_code_quality(sdk_path)
    logger.info(
        f"Code Quality: {cq_result['status']} "
        f"({cq_result['issue_count']} issues)"
    )

    if args.evaluate:
        gt_path = "tests/ground_truth/jsonplaceholder.yaml"
        metrics = compute_extraction_accuracy(schema, gt_path)
        logger.info(f"Evaluation Metrics: {metrics}")

    if args.smoke_test:
        test_calls = [("get_posts", {}), ("get_users", {})]
        smoke_result = smoke_test_sdk(sdk_path, test_calls)
        logger.info(f"Smoke Test Summary: {smoke_result}")


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
    sdk_path = generate_sdk(schema)

    logger.info(
        f"Parsed OpenAPI Spec: {schema.title} "
        f"({len(schema.endpoints)} endpoints)"
    )
    logger.info(f"Generated SDK path: {sdk_path}")

    cq_result = check_code_quality(sdk_path)
    logger.info(
        f"Code Quality Check: {cq_result['status']} "
        f"({cq_result['issue_count']} issues)"
    )


def main() -> None:
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
            "Missing required input. "
            "Must provide --url, --urls, or --spec."
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
