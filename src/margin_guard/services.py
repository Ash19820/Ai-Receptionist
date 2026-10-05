from __future__ import annotations

import json


def audit_in_conn(conn, action: str, entity_type: str, entity_id: int | str, details: dict) -> None:
    conn.execute(
        "INSERT INTO audit_log(action,entity_type,entity_id,details) VALUES(?,?,?,?)",
        (action, entity_type, str(entity_id), json.dumps(details, sort_keys=True)),
    )
