"""In-memory audit log.

Stores one entry per mutating action. Kept separate from the main store
intentionally — audit logs should be append-only and never mutated,
even in a mock. In production this would be a time-series store
(e.g. ClickHouse or Tinybird) partitioned by ts.

Retention: in-memory only. A production implementation would enforce
a retention policy (e.g. 90 days for standard, 1 year for enterprise)
at the storage layer, not in application code.

Migration path — app-layer to CDC:
This implementation captures audit events by calling add_entry() explicitly
in each route handler. That works for a mock but has a production gap: any
mutation that bypasses the application layer (direct DB queries, migrations,
admin tooling) is invisible to this log.

The production end state is CDC (Change Data Capture) via Postgres logical
replication + Debezium. Every INSERT/UPDATE/DELETE on api_keys, deployments,
and spend_limits emits a change event automatically at the DB layer —
no engineer discipline required, no missed calls. The add_entry() interface
here intentionally mirrors the shape of a CDC event (before, after, resource_id,
ts) so the migration is a drop-in: swap the sink, keep the schema.
"""
from __future__ import annotations

import threading
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any


class AuditLog:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._entries: list[dict[str, Any]] = []

    def add_entry(
        self,
        *,
        actor: str,
        action: str,
        resource_id: str,
        before: dict | None,
        after: dict | None,
        ip: str,
        user_agent: str,
    ) -> dict:
        # Quick solution: caller explicitly logs each mutation. This requires
        # every engineer to remember to call add_entry() on new mutating endpoints.
        # Scalable solution: replace with CDC (Postgres logical replication +
        # Debezium) so mutations are captured automatically at the DB layer,
        # regardless of what code path caused them.
        entry = {
            "id": str(uuid.uuid4()),
            "actor": actor,
            "action": action,
            "resource_id": resource_id,
            "before": before,
            "after": after,
            "ip": ip,
            "user_agent": user_agent,
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        }
        with self._lock:
            self._entries.append(entry)
        return deepcopy(entry)

    def list_entries(
        self,
        *,
        actor: str | None = None,
        action: str | None = None,
    ) -> list[dict]:
        with self._lock:
            entries = deepcopy(self._entries)
        if actor:
            entries = [e for e in entries if e["actor"] == actor]
        if action:
            entries = [e for e in entries if e["action"] == action]
        return entries


audit_log = AuditLog()
