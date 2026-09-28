"""Model Context Protocol adapter for ContextPlane."""

from contextplane.mcp.server import (
    ContextPlaneEntraTokenVerifier,
    build_mcp_server,
    build_mcp_server_from_settings,
)

__all__ = [
    "ContextPlaneEntraTokenVerifier",
    "build_mcp_server",
    "build_mcp_server_from_settings",
]
