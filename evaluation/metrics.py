import logging
import subprocess
import time
from typing import Any, Dict
import yaml
from parser.models import APISchema

logger = logging.getLogger("smart_api_tool")


class LatencyTracker:
    def __init__(self):
        self._stages: Dict[str, float] = {}
        self._start_times: Dict[str, float] = {}

    def start(self, stage: str):
        self._start_times[stage] = time.time()

    def stop(self, stage: str):
        if stage in self._start_times:
            elapsed = time.time() - self._start_times[stage]
            self._stages[stage] = round(elapsed, 3)
            logger.info(f"Stage '{stage}' took {self._stages[stage]}s")

    def report(self) -> Dict[str, Any]:
        total = round(sum(self._stages.values()), 3)
        return {"stages": self._stages, "total_seconds": total}


def compute_extraction_accuracy(
    schema: APISchema, ground_truth_path: str
) -> Dict[str, Any]:
    with open(ground_truth_path, "r", encoding="utf-8") as f:
        gt_data = yaml.safe_load(f)

    gt_set = set()
    for ep in gt_data.get("endpoints", []):
        gt_set.add((ep.get("path"), ep.get("method", "").upper()))

    extracted_set = set()
    for ep in schema.endpoints:
        extracted_set.add((ep.path, ep.method.upper()))

    tp = gt_set.intersection(extracted_set)
    missed = gt_set - extracted_set
    hallucinated = extracted_set - gt_set

    precision = len(tp) / len(extracted_set) if extracted_set else 0.0
    recall = len(tp) / len(gt_set) if gt_set else 0.0
    f1 = (
        (2 * precision * recall) / (precision + recall)
        if (precision + recall) > 0
        else 0.0
    )

    logger.info(
        f"Precision: {precision:.2f}, Recall: {recall:.2f}, F1: {f1:.2f}"
    )

    return {
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "f1": round(f1, 3),
        "missed": sorted(list(missed)),
        "hallucinated": sorted(list(hallucinated)),
    }


def check_code_quality(sdk_path: str) -> Dict[str, Any]:
    result = subprocess.run(
        ["flake8", "--max-line-length=100", sdk_path],
        capture_output=True,
        text=True,
    )

    if result.returncode == 0:
        status = "PASS"
        issues = []
    else:
        status = "FAIL"
        issues = [line for line in result.stdout.split("\n") if line.strip()]

    logger.info(f"Code Quality Check: {status} ({len(issues)} issues found)")

    return {
        "status": status,
        "issue_count": len(issues),
        "issues": issues,
    }
