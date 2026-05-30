"""Audit log endpoint.

GET /v1/audits — lists audit entries, filterable by actor and action.
Mock-only surface; does not exist in production yet.
"""
from __future__ import annotations

from fastapi import APIRouter, Query

from audit_log import audit_log

router = APIRouter(prefix="/v1", tags=["audits"])


@router.get("/audits")
async def list_audits(
    actor: str | None = Query(None, description="Filter by actor (API key prefix)."),
    action: str | None = Query(None, description="Filter by action (e.g. api_key.created)."),
):
    entries = audit_log.list_entries(actor=actor, action=action)
    return {"object": "list", "count": len(entries), "data": entries}
