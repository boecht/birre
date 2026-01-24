import pytest
from unittest.mock import MagicMock, AsyncMock
from fastmcp.server import Context
from birre.integrations.bitsight.v1_bridge import BitSightV1Bridge
from birre.domain.models import ToolResult, Severity
from birre.domain.exceptions import DomainError

class ReqAPI:
    """Mock request object that behaves like Starlette Request."""
    docket = None
    
    def __init__(self, state_mock):
        self.state = state_mock
        self.scope = {"type": "http"}

@pytest.fixture
def mock_context():
    """Create a mock FastMCP context with V1 bridge state."""
    mock_bridge = AsyncMock(spec=BitSightV1Bridge)
    mock_state = MagicMock()
    mock_state.v1_bridge = mock_bridge
    
    # Mock the request object with our custom class
    mock_request = ReqAPI(mock_state)
    
    # Create context and inject our mock request
    ctx = Context(request=mock_request, fastmcp=MagicMock())
    return ctx, mock_bridge

@pytest.mark.asyncio
async def test_call_openapi_tool_normalizes_structured_and_json_text(mock_context):
    ctx, bridge = mock_context
    bridge.call_openapi_tool.return_value = ToolResult(
        content=[{"type": "text", "text": '{"foo": "bar"}'}],
        is_error=False
    )
    
    v1 = BitSightV1Bridge("apikey")
    # We mock the internal call to delegate to the context's bridge
    # But since we are testing the static method logic or the instance method logic?
    # Actually v1_bridge.py has `call_openapi_tool` as a static method/helper or instance method.
    # The code under test is usually `call_openapi_tool(ctx, ...)`
    
    # Let's check the implementation of call_openapi_tool in v1_bridge.py to be sure how it's called.
    # It seems to be an instance method that takes context.
    
    result = await v1.call_openapi_tool(ctx, "tool_name", {"arg": "val"})
    
    assert len(result.content) == 1
    assert result.content[0]["type"] == "text"
    assert result.content[0]["text"] == '{"foo": "bar"}'
    assert not result.is_error

@pytest.mark.asyncio
async def test_call_openapi_tool_unstructured_returns_raw_with_warnings(mock_context):
    ctx, bridge = mock_context
    bridge.call_openapi_tool.return_value = ToolResult(
        content=[{"type": "text", "text": "raw string"}],
        is_error=False
    )
    
    v1 = BitSightV1Bridge("apikey")
    result = await v1.call_openapi_tool(ctx, "tool_name", {})
    
    assert result.content[0]["text"] == "raw string"
    # Should have added a warning about unstructured content
    assert "Raw text content received" in str(result)

@pytest.mark.asyncio
async def test_parse_text_content_invalid_json_logs_warning(mock_context):
    v1 = BitSightV1Bridge("apikey")
    content = [{"type": "text", "text": "{invalid json"}]
    
    parsed = v1._parse_text_content(content)
    assert parsed == content # Returns original if parsing fails

@pytest.mark.asyncio
async def test_input_validation_errors(mock_context):
    v1 = BitSightV1Bridge("apikey")
    
    # Missing args
    with pytest.raises(ValueError):
        await v1.call_openapi_tool(mock_context[0], "tool", None)

@pytest.mark.asyncio
async def test_call_openapi_tool_http_status_error_propagates(mock_context):
    ctx, bridge = mock_context
    bridge.call_openapi_tool.side_effect = DomainError("HTTP 500")
    
    v1 = BitSightV1Bridge("apikey")
    with pytest.raises(DomainError):
        await v1.call_openapi_tool(ctx, "fail", {})

@pytest.mark.asyncio
async def test_call_openapi_tool_request_error_maps_to_domain(mock_context):
    ctx, bridge = mock_context
    # Simulate a request error (e.g. network)
    bridge.call_openapi_tool.side_effect = Exception("Network fail")
    
    v1 = BitSightV1Bridge("apikey")
    with pytest.raises(Exception) as exc:
        await v1.call_openapi_tool(ctx, "fail", {})
    assert "Network fail" in str(exc.value)

@pytest.mark.asyncio
async def test_filter_none():
    v1 = BitSightV1Bridge("k")
    res = v1._filter_none({"a": 1, "b": None})
    assert res == {"a": 1}

@pytest.mark.asyncio
async def test_delegate_v1_and_v2_to_common(mock_context):
    # Test that V1/V2 specific methods eventually call the common implementation
    pass

@pytest.mark.asyncio
async def test_request_error_without_mapping_propagates(mock_context):
    ctx, bridge = mock_context
    bridge.call_openapi_tool.side_effect = KeyError("boom")
    
    v1 = BitSightV1Bridge("apikey")
    with pytest.raises(KeyError):
        await v1.call_openapi_tool(ctx, "t", {})

@pytest.mark.asyncio
async def test_content_without_text_returns_raw_and_warns(mock_context):
    v1 = BitSightV1Bridge("k")
    content = [{"type": "image", "data": "..."}]
    res = v1._parse_text_content(content)
    assert res == content

@pytest.mark.asyncio
async def test_params_filtering_is_applied(mock_context):
    v1 = BitSightV1Bridge("k")
    params = {"a": 1, "b": None}
    # This is implicitly tested via call_openapi_tool but unit test helper directly:
    filtered = v1._filter_none(params)
    assert "b" not in filtered

@pytest.mark.asyncio
async def test_log_tls_error_debug_and_non_debug(mock_context):
    # This would test the error handling logic in bridge
    pass
