import json
from pathlib import Path

CONFIG = Path("examples/coding-agent/.cursor/mcp.json")


def test_cursor_demo_config_uses_remote_mcp_and_environment_interpolation() -> None:
    payload = json.loads(CONFIG.read_text(encoding="utf-8"))
    contextplane = payload["mcpServers"]["contextplane"]

    assert contextplane["url"] == "${env:CONTEXTPLANE_MCP_URL}"
    assert contextplane["auth"]["CLIENT_ID"] == (
        "${env:CONTEXTPLANE_CURSOR_CLIENT_ID}"
    )
    assert contextplane["auth"]["scopes"] == ["context.resolve"]
    assert "CLIENT_SECRET" not in contextplane["auth"]


def test_cursor_demo_config_contains_no_committed_bearer_or_secret() -> None:
    raw = CONFIG.read_text(encoding="utf-8").lower()

    assert "authorization" not in raw
    assert "bearer " not in raw
    assert "client_secret" not in raw
