from __future__ import annotations

import re

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from margin_guard.db import connect, initialize
from margin_guard.services import audit_in_conn


mcp = MCPServer("receptionist-request-inbox")
REQUEST_TYPES = {"appointment", "callback", "information", "other"}


@mcp.tool(annotations=ToolAnnotations(read_only_hint=True, open_world_hint=False))
def get_open_requests(limit: int = 25) -> list[dict]:
    """Show recent unreviewed caller requests for the business owner or receptionist."""
    initialize()
    safe_limit = min(max(int(limit), 1), 100)
    with connect() as conn:
        return [dict(row) for row in conn.execute(
            "SELECT id,caller_name,caller_phone,request_type,service,preferred_time,summary,status,source,created_at "
            "FROM receptionist_requests WHERE status='needs_review' ORDER BY id DESC LIMIT ?",
            (safe_limit,),
        )]


@mcp.tool(annotations=ToolAnnotations(destructive_hint=False, idempotent_hint=False, open_world_hint=False))
def create_caller_request(
    request_type: str,
    summary: str,
    caller_confirmed: bool,
    caller_name: str = "",
    caller_phone: str = "",
    service: str = "",
    preferred_time: str = "",
    source: str = "demo",
) -> dict:
    """Create a review-needed request only after the caller explicitly confirms the read-back. This is not a confirmed appointment or price quote."""
    initialize()
    if caller_confirmed is not True:
        raise ValueError("The caller must explicitly confirm the read-back before a request can be saved.")
    request_type = request_type.strip().lower()
    if request_type not in REQUEST_TYPES:
        raise ValueError(f"request_type must be one of: {', '.join(sorted(REQUEST_TYPES))}")
    summary = summary.strip()
    if not summary:
        raise ValueError("A short summary of the caller's request is required.")
    phone = caller_phone.strip()
    if phone and (len(phone) > 24 or not re.fullmatch(r"[+0-9() .-]+", phone)):
        raise ValueError("Phone number has an invalid format.")
    source = source.strip().lower()
    if source not in {"demo", "phone", "web", "whatsapp"}:
        source = "demo"
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO receptionist_requests(caller_name,caller_phone,request_type,service,preferred_time,summary,source) "
            "VALUES(?,?,?,?,?,?,?)",
            (caller_name.strip(), phone, request_type, service.strip(), preferred_time.strip(), summary, source),
        )
        request_id = cur.lastrowid
        audit_in_conn(conn, "caller_request_created", "receptionist_request", request_id,
                      {"request_type": request_type, "source": source})
    return {"request_id": request_id, "status": "needs_review", "request_type": request_type,
            "message": "Request saved for business review. It is not a confirmed booking."}


if __name__ == "__main__":
    initialize()
    mcp.run(transport="stdio")
