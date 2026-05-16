import time
from evaluation.metrics import LatencyTracker


def test_latency_tracker_records_stages():
    """Verify that the LatencyTracker correctly starts, stops, and generates a latency report."""
    tracker = LatencyTracker()

    tracker.start("test_stage")
    time.sleep(0.01)  # tiny delay to ensure latency > 0
    tracker.stop("test_stage")

    report = tracker.report()

    assert "test_stage" in report["stages"]
    assert report["stages"]["test_stage"] > 0.0
    assert "total_seconds" in report
    assert report["total_seconds"] > 0.0
