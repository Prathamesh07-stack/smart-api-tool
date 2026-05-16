import os
from parser.models import APISchema
from generator.codegen import generate_sdk


def test_generates_output_file(tmp_path):
    """Verify that generate_sdk successfully creates a .py file."""
    schema_dict = {
        "title": "TestCodegenAPI",
        "version": "1.0.0",
        "base_url": "https://api.test.com",
        "auth": {"type": "none"},
        "endpoints": [
            {
                "path": "/data",
                "method": "GET",
                "summary": "Get data",
                "parameters": [],
                "response_description": "Data",
            }
        ],
    }
    schema = APISchema(**schema_dict)

    # We will temporarily override the output directory to use tmp_path
    # generate_sdk takes output_dir="output" by default
    output_file_path = generate_sdk(schema, output_dir=str(tmp_path))

    assert os.path.exists(output_file_path)
    assert output_file_path.endswith(".py")

    with open(output_file_path, "r", encoding="utf-8") as f:
        content = f.read()
        assert "class TestCodegenAPIClient:" in content
        assert "def get_data(" in content
