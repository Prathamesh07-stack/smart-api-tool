import logging
import requests

from typing import Any, Dict, List, Literal, Optional

from .models import APIEndpoint, APIParameter, APISchema, AuthMethod

logger = logging.getLogger("smart_api_tool")

INTROSPECTION_QUERY = """
query IntrospectionQuery {
  __schema {
    queryType { name }
    mutationType { name }
    types {
      name
      kind
      fields(includeDeprecated: true) {
        name
        description
        args {
          name
          description
          type {
            kind
            name
            ofType {
              kind
              name
              ofType {
                kind
                name
              }
            }
          }
        }
      }
    }
  }
}
"""


def _resolve_type_name(type_obj: Optional[Dict]) -> str:
    """Recursively resolves GraphQL type name (handles NON_NULL and LIST)."""
    if type_obj is None:
        return "string"
    kind = type_obj.get("kind", "")
    name = type_obj.get("name")
    if name:
        return name.lower()
    if kind in ("NON_NULL", "LIST"):
        return _resolve_type_name(type_obj.get("ofType"))
    return "string"


def _is_required(type_obj: Optional[Dict]) -> bool:
    """Returns True if the GraphQL type is NON_NULL (required)."""
    if type_obj is None:
        return False
    return type_obj.get("kind") == "NON_NULL"


def fetch_graphql_schema(
    url: str, headers: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """POSTs the introspection query to the GraphQL endpoint and returns data."""
    if headers is None:
        headers = {}
    headers["Content-Type"] = "application/json"

    try:
        response = requests.post(
            url,
            json={"query": INTROSPECTION_QUERY},
            headers=headers,
            timeout=30,
        )
        response.raise_for_status()
        response_json = response.json()
        logger.info("GraphQL introspection succeeded for %s", url)
        return response_json["data"]
    except Exception as exc:
        logger.error("GraphQL introspection failed for %s: %s", url, exc)
        raise


def parse_graphql_schema(
    schema_dict: Dict[str, Any],
    endpoint_url: str,
    headers: Optional[Dict[str, str]] = None,
) -> APISchema:
    """Converts a raw GraphQL introspection result into an APISchema."""
    if headers is None:
        headers = {}

    raw_schema = schema_dict.get("__schema", {})
    all_types: List[Dict] = raw_schema.get("types", [])

    query_type_name = (raw_schema.get("queryType") or {}).get("name", "Query")
    mutation_type_name = (raw_schema.get("mutationType") or {}).get(
        "name", "Mutation"
    )

    type_map = {t["name"]: t for t in all_types if t.get("name")}

    endpoints: List[APIEndpoint] = []

    for type_name, http_method in [
        (query_type_name, "GET"),
        (mutation_type_name, "POST"),
    ]:
        http_method_literal: Literal["GET", "POST"] = http_method  # type: ignore[assignment]
        root_type = type_map.get(type_name)
        if not root_type:
            continue
        for field in root_type.get("fields") or []:
            parameters: List[APIParameter] = []
            for arg in field.get("args") or []:
                parameters.append(
                    APIParameter(
                        name=arg["name"],
                        type=_resolve_type_name(arg.get("type")),
                        required=_is_required(arg.get("type")),
                        description=arg.get("description") or "",
                        location="body",
                    )
                )
            endpoints.append(
                APIEndpoint(
                    path=endpoint_url,
                    method=http_method_literal,
                    summary=field.get("description") or field["name"],
                    parameters=parameters,
                    response_description="GraphQL field response",
                )
            )

    auth_header = headers.get("Authorization", "")
    if auth_header:
        auth = AuthMethod(type="bearer", header_name="Authorization")
    else:
        auth = AuthMethod(type="none")

    from urllib.parse import urlparse as _urlparse

    hostname = _urlparse(endpoint_url).hostname or "graphql_api"
    clean_name = hostname.replace(".", "_").replace("-", "_")
    title = f"GraphQL_{clean_name}"

    return APISchema(
        title=title,
        base_url=endpoint_url,
        version="1.0",
        auth=auth,
        endpoints=endpoints,
        confidence_score=1.0,
        extraction_notes=["Parsed from GraphQL introspection — high confidence"],
    )


def parse_graphql_url(url: str, api_key: str = "") -> APISchema:
    """Convenience wrapper: introspects a GraphQL URL and returns an APISchema."""
    headers: Dict[str, str] = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    schema_dict = fetch_graphql_schema(url, headers=headers)
    return parse_graphql_schema(schema_dict, endpoint_url=url, headers=headers)
