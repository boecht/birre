from __future__ import annotations

from src.apis import clients


def test_schema_responses_are_wrapped_as_proper_objects() -> None:
    spec = clients._load_api_spec("apis/bitsight.v1.schema.json")

    responses = (
        spec["paths"]["/companies/{company_guid}/exposed-credentials/credentials"]["get"]["responses"]
    )

    for status in ("400", "422"):
        response = responses[status]
        assert "$ref" not in response
        assert response["description"], f"missing description for {status}"
        media_types = response.get("content", {})
        assert "application/json" in media_types
        schema_ref = media_types["application/json"]["schema"]["$ref"]
        assert schema_ref == "#/components/schemas/ExposedCredentialsLeak"
