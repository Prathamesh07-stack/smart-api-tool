import importlib.util
import logging
import os
from typing import Any, Dict, List, Tuple

logger = logging.getLogger("smart_api_tool")


def smoke_test_sdk(
    sdk_path: str, test_calls: List[Tuple[str, Dict[str, Any]]]
) -> Dict[str, Any]:
    if not os.path.exists(sdk_path):
        logger.error(f"SDK path not found: {sdk_path}")
        return {
            "passed": 0,
            "total": len(test_calls),
            "details": [{"error": "File not found"}],
        }

    try:
        spec = importlib.util.spec_from_file_location(
            "generated_sdk", sdk_path
        )
        if spec is None or spec.loader is None:
            raise ImportError(f"Could not load spec from {sdk_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except Exception as e:
        logger.error(f"Failed to import SDK: {e}")
        return {
            "passed": 0,
            "total": len(test_calls),
            "details": [{"error": f"Import failed: {e}"}],
        }

    client_class_name = None
    for name in dir(module):
        if "Client" in name:
            client_class_name = name
            break

    if not client_class_name:
        logger.error("No Client class found in SDK.")
        return {
            "passed": 0,
            "total": len(test_calls),
            "details": [{"error": "Client class missing"}],
        }

    ClientClass = getattr(module, client_class_name)
    try:
        client = ClientClass()
    except Exception as e:
        logger.error(f"Failed to instantiate client: {e}")
        return {
            "passed": 0,
            "total": len(test_calls),
            "details": [{"error": f"Instantiation failed: {e}"}],
        }

    details = []
    passed = 0

    for method_name, kwargs in test_calls:
        if not hasattr(client, method_name):
            details.append(
                {
                    "method": method_name,
                    "status": "FAIL",
                    "error": "Method not found on client",
                }
            )
            logger.error(
                f"Smoke test failed for {method_name}: Method not found"
            )
            continue

        try:
            getattr(client, method_name)(**kwargs)
            details.append({"method": method_name, "status": "PASS"})
            passed += 1
            logger.info(f"Smoke test passed for {method_name}")
        except Exception as exc:
            logger.error(f"Smoke test failed for {method_name}: {exc}")
            details.append(
                {"method": method_name, "status": "FAIL", "error": str(exc)}
            )

    return {"passed": passed, "total": len(test_calls), "details": details}
