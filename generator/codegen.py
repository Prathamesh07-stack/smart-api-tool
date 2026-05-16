import logging
import os
import re
import subprocess

from jinja2 import Environment, FileSystemLoader

from parser.models import APISchema

logger = logging.getLogger("smart_api_tool")


def sanitize_filename(title: str, ext: str = ".py") -> str:
    """Lowercases and replaces illegal characters to build a safe filename."""
    clean = re.sub(r"[^a-zA-Z0-9]+", "_", title.lower())
    clean = clean.strip("_")
    if not clean:
        clean = "api"
    return f"{clean}_sdk{ext}"


def _class_name(title: str) -> str:
    """Derives a clean class name by stripping all non-alphanumeric characters."""
    return re.sub(r"[^a-zA-Z0-9]", "", title)


def format_method_name(method: str, path: str) -> str:
    """Converts GET /users/{id} -> get_users_id."""
    clean_path = re.sub(r"[^a-zA-Z0-9]+", "_", path).strip("_")
    if not clean_path:
        return method.lower()
    return f"{method.lower()}_{clean_path}"


def safe_param_name(name: str) -> str:
    """Sanitizes parameter names to avoid Python keywords."""
    import keyword

    clean = re.sub(r"[^a-zA-Z0-9_]+", "_", name).strip("_")
    if keyword.iskeyword(clean) or not clean.isidentifier():
        return f"{clean}_"
    return clean


def to_python_type(type_str: str) -> str:
    """Map OpenAPI types to Python types."""
    t = type_str.lower() if type_str else "string"
    if t in ["integer", "int"]:
        return "int"
    if t in ["number", "float"]:
        return "float"
    if t in ["boolean", "bool"]:
        return "bool"
    if t in ["array", "list"]:
        return "list"
    if t in ["object", "dict"]:
        return "dict"
    return "str"


def generate_sdk(
    schema: APISchema,
    output_dir: str = "output",
    language: str = "python",
) -> str:
    """Renders the APISchema into an SDK using Jinja2 for the target language."""
    os.makedirs(output_dir, exist_ok=True)

    templates_dir = os.path.join(os.path.dirname(__file__), "templates")
    env = Environment(
        loader=FileSystemLoader(templates_dir),
        trim_blocks=True,
        lstrip_blocks=True,
    )

    # Register custom filters
    env.filters["format_method_name"] = format_method_name
    env.filters["safe_param_name"] = safe_param_name
    env.filters["to_python_type"] = to_python_type

    if language == "javascript":
        template_name = "javascript_sdk.jinja2"
        filename = sanitize_filename(schema.title, ext=".js")
    else:
        template_name = "python_sdk.jinja2"
        filename = sanitize_filename(schema.title, ext=".py")

    logger.info(f"Generating {language} SDK...")
    template = env.get_template(template_name)
    output_path = os.path.abspath(os.path.join(output_dir, filename))

    # Deduplicate endpoints to prevent F811 (redefinition of unused function)
    seen_methods = set()
    unique_endpoints = []
    for ep in schema.endpoints:
        m_name = format_method_name(ep.method, ep.path)
        if m_name not in seen_methods:
            seen_methods.add(m_name)
            unique_endpoints.append(ep)
    schema.endpoints = unique_endpoints

    class_name = _class_name(schema.title) + "Client"
    first_method = (
        format_method_name(
            schema.endpoints[0].method, schema.endpoints[0].path
        )
        if schema.endpoints
        else ""
    )

    rendered_code = template.render(
        schema=schema,
        class_name=class_name,
        first_method_name=first_method,
    )

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(rendered_code)

    if language == "python":
        try:
            subprocess.run(
                [
                    "autoflake",
                    "--in-place",
                    "--remove-all-unused-imports",
                    output_path,
                ],
                check=True,
            )
            subprocess.run(
                ["black", "-q", "--line-length=79", output_path],
                check=True,
            )
        except Exception as e:
            logger.warning(f"Auto-formatting failed for {output_path}: {e}")

    logger.info(f"SDK generated at: {output_path}")
    return output_path
