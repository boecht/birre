from __future__ import annotations

from birre.integrations.bitsight import client


def test_schema_responses_are_wrapped_as_proper_objects() -> None:
    spec = client._load_api_spec("bitsight.v1.schema.json")

    responses = spec["paths"]["/companies/{company_guid}/exposed-credentials/credentials"]["get"][
        "responses"
    ]

    for status in ("400", "422"):
        response = responses[status]
        assert "$ref" not in response
        assert response["description"], f"missing description for {status}"
        media_types = response.get("content", {})
        assert "application/json" in media_types
        schema_ref = media_types["application/json"]["schema"]["$ref"]
        assert schema_ref == "#/components/schemas/ExposedCredentialsLeak"


def test_sanitize_null_properties_strips_upstream_quirks() -> None:
    """Verify _sanitize_null_properties removes 'properties: null' from schema nodes."""
    node = {
        "$ref": "#/components/schemas/Foo",
        "properties": None,
    }
    result = client._sanitize_null_properties(node)
    assert "properties" not in result
    assert result == {"$ref": "#/components/schemas/Foo"}

    # Nested structures are sanitized recursively
    nested = {"items": {"$ref": "#/x", "properties": None}, "type": "array"}
    assert client._sanitize_null_properties(nested) == {
        "items": {"$ref": "#/x"},
        "type": "array",
    }

    # Non-null properties are preserved
    valid = {"properties": {"name": {"type": "string"}}}
    assert client._sanitize_null_properties(valid) == valid

    # Lists with dicts are sanitized
    array = [{"$ref": "#/y", "properties": None}, "leaf"]
    assert client._sanitize_null_properties(array) == [{"$ref": "#/y"}, "leaf"]


def test_loaded_v1_spec_has_no_null_properties() -> None:
    """Ensure the loaded v1 spec contains no 'properties: null' after sanitization."""
    import json

    spec = client._load_api_spec("bitsight.v1.schema.json")
    serialized = json.dumps(spec)
    assert '"properties": null' not in serialized
