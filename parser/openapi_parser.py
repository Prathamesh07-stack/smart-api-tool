import json
import logging
import os
from typing import Any, Dict

import yaml

from .models import APIEndpoint, APIParameter, APISchema, AuthMethod

logger = logging.getLogger("smart_api_tool")


def load_spec(path: str) -> Dict[str, Any]:
    """Load an OpenAPI spec from a JSON or YAML file."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"Spec file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        if path.lower().endswith(".json"):
            spec = json.load(f)
        else:
            spec = yaml.safe_load(f)

    v3 = spec.get("openapi", "")
    v2 = spec.get("swagger", "")
    if v3:
        logger.info(f"Loaded OpenAPI v3 spec: {v3}")
    elif v2:
        logger.info(f"Loaded Swagger v2 spec: {v2}")
    else:
        logger.warning("Could not determine OpenAPI version from spec.")

    return spec


def parse_openapi_file(path: str) -> APISchema:
    """Parse an OpenAPI v2/v3 spec file into an APISchema."""
    spec = load_spec(path)

    # 1. Determine version
    is_v3 = str(spec.get("openapi", "")).startswith("3")
    is_v2 = str(spec.get("swagger", "")).startswith("2")

    if not is_v3 and not is_v2:
        is_v3 = True  # Fallback assumption

    # 2. Extract Base URL & Version
    info = spec.get("info", {})
    title = info.get("title", "Unknown API")
    version_str = info.get("version", "1.0")

    if is_v3:
        servers = spec.get("servers", [])
        base_url = servers[0].get("url", "") if servers else ""
    else:
        schemes = spec.get("schemes", ["https"])
        scheme = schemes[0] if schemes else "https"
        host = spec.get("host", "")
        base_path = spec.get("basePath", "")
        base_url = f"{scheme}://{host}{base_path}" if host else ""

    logger.info(f"Base URL determined as: {base_url}")

    # 3. Auth Extraction
    auth_method = AuthMethod(type="none")
    if is_v3:
        security_schemes = spec.get("components", {}).get(
            "securitySchemes", {}
        )
        for name, scheme_obj in security_schemes.items():
            scheme_type = scheme_obj.get("type")
            if scheme_type == "http" and scheme_obj.get(
                "scheme", ""
            ).lower() == "bearer":
                auth_method = AuthMethod(
                    type="bearer", header_name="Authorization"
                )
                break
            elif scheme_type == "apiKey" and scheme_obj.get("in") == "header":
                auth_method = AuthMethod(
                    type="api_key",
                    header_name=scheme_obj.get("name", "X-API-Key"),
                )
                break
    else:
        security_defs = spec.get("securityDefinitions", {})
        for name, def_obj in security_defs.items():
            def_type = def_obj.get("type")
            if def_type == "apiKey" and def_obj.get("in") == "header":
                auth_method = AuthMethod(
                    type="api_key",
                    header_name=def_obj.get("name", "X-API-Key"),
                )
                break
            elif def_type == "oauth2":
                auth_method = AuthMethod(
                    type="bearer", header_name="Authorization"
                )
                break

    # 4. Paths -> Endpoints
    endpoints = []
    paths = spec.get("paths", {})
    valid_methods = {"get", "post", "put", "delete", "patch"}

    for path_str, path_item in paths.items():
        if not isinstance(path_item, dict):
            continue

        path_params = path_item.get("parameters", [])

        for method_key, operation in path_item.items():
            if method_key.lower() not in valid_methods:
                continue

            method_upper = method_key.upper()
            summary = (
                operation.get("summary")
                or operation.get("operationId")
                or ""
            )

            op_params = operation.get("parameters", [])
            all_params_raw = path_params + op_params

            parameters = []
            for param in all_params_raw:
                if "$ref" in param:
                    continue

                name = param.get("name", "unknown")
                location = param.get("in", "query")
                if location not in ["query", "path", "header", "body"]:
                    location = "query"

                required = param.get("required", False)
                description = param.get("description", "")

                param_type = "string"
                if is_v3:
                    schema_obj = param.get("schema", {})
                    param_type = schema_obj.get("type", "string")
                else:
                    param_type = param.get("type", "string")

                parameters.append(
                    APIParameter(
                        name=name,
                        type=param_type,
                        required=required,
                        description=description,
                        location=location,
                    )
                )

            response_desc = None
            responses = operation.get("responses", {})
            success_resp = (
                responses.get("200")
                or responses.get("201")
                or responses.get("default")
            )
            if success_resp and isinstance(success_resp, dict):
                response_desc = success_resp.get("description")

            endpoints.append(
                APIEndpoint(
                    path=path_str,
                    method=method_upper,
                    summary=summary,
                    parameters=parameters,
                    response_description=response_desc,
                )
            )

    return APISchema(
        title=title,
        base_url=base_url,
        version=version_str,
        auth=auth_method,
        endpoints=endpoints,
        confidence_score=1.0,
        extraction_notes=[
            "Parsed explicitly from OpenAPI specification file."
        ],
    )
