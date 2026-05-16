from parser.models import APISchema


def test_valid_schema_parses():
    """Verify that APISchema successfully parses a valid dictionary into a Pydantic model."""
    valid_dict = {
        "title": "Test API",
        "version": "1.0.0",
        "base_url": "https://api.test.com",
        "auth": {"type": "none"},
        "endpoints": [
            {
                "path": "/users",
                "method": "GET",
                "summary": "Get all users",
                "parameters": [
                    {
                        "name": "limit",
                        "type": "integer",
                        "required": False,
                        "description": "Max users to return",
                    }
                ],
                "response_description": "List of users",
            }
        ],
    }

    schema = APISchema(**valid_dict)
    assert schema.title == "Test API"
    assert len(schema.endpoints) == 1
    assert schema.endpoints[0].method == "GET"
    assert schema.endpoints[0].parameters[0].name == "limit"
