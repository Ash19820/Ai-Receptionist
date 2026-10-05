from __future__ import annotations

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from margin_guard.db import initialize
from margin_guard.receptionist_profile import find_faqs, load_profile


mcp = MCPServer("receptionist-business-info")


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False))
def get_business_profile() -> dict:
    """Return verified business name, hours, service area, supported languages, and handoff rules for this receptionist."""
    initialize()
    profile = load_profile()
    return {key: profile.get(key) for key in (
        "business_name", "business_type", "timezone", "languages", "greeting",
        "human_handoff_phone", "hours", "service_area", "policies",
    )}


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False))
def list_business_services() -> list[dict]:
    """List the business's configured services and confirmed prices or durations, if present."""
    initialize()
    return load_profile().get("services", [])


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False))
def search_business_faq(query: str) -> list[dict[str, str]]:
    """Search only the owner-provided FAQ. An empty result means the receptionist should ask staff instead of guessing."""
    initialize()
    return find_faqs(query)


if __name__ == "__main__":
    initialize()
    mcp.run(transport="stdio")
