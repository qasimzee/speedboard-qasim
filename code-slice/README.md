# Code Slice — C: Audit Log

## Why this slice

I chose the audit log because it sits at the center of my headline recommendation: harden the gateway layer and make it the single enforcement and observability boundary. An audit log is the first concrete output of that boundary — every mutating action leaves a record of who did what, to what, and when. It is also the foundation for the customer-facing observability I recommend in the phased rollout: you cannot show customers their request history without first capturing it.

## How to run

```bash
docker compose up --build
```

The mock backend starts at `http://localhost:3001`.

Run the smoke test (requires server to be running):

```bash
python3 code-slice/smoke_test.py
```

Try it manually:

```bash
# Create an API key (writes an audit entry)
curl -s -X POST http://localhost:3001/v1/api-keys \
  -H "Authorization: Bearer psk-mock-mockkey" \
  -H "Content-Type: application/json" \
  -d '{"name": "my-key", "scopes": ["inference:read"]}'

# Query the audit log
curl -s http://localhost:3001/v1/audits \
  -H "Authorization: Bearer psk-mock-mockkey"

# Filter by action
curl -s "http://localhost:3001/v1/audits?action=api_key.created" \
  -H "Authorization: Bearer psk-mock-mockkey"

# Filter by actor
curl -s "http://localhost:3001/v1/audits?actor=psk-mock-" \
  -H "Authorization: Bearer psk-mock-mockkey"
```

## What was built

- `backend/mock-server/audit_log.py` — append-only in-memory audit log. Thread-safe. Each entry captures: `id`, `actor`, `action`, `resource_id`, `before`, `after`, `ip`, `user_agent`, `ts`.
- `backend/mock-server/routes/audits.py` — `GET /v1/audits` endpoint, filterable by `actor` and `action`.
- Wired into all mutating endpoints: `POST /v1/api-keys`, `PATCH /v1/api-keys/:id`, `DELETE /v1/api-keys/:id`, `POST /v1/deployments`, `DELETE /v1/deployments/:id`, `POST /v1/spend-limits`.

## Tradeoffs

- **In-memory, not persisted.** The audit log resets on restart. Chosen deliberately — the goal is to show the shape of the log and the wiring, not to solve persistence. In production this would be a time-series store (Tinybird or ClickHouse) with a retention policy enforced at the storage layer.
- **Actor is the API key prefix, not a user identity.** The mock has no real identity system — no login, no sessions. Using the key prefix (`psk-mock-`) is the best available signal. In production, actor would be a resolved user ID or service identity from a real auth layer.
- **Separate module, not inside the store.** The audit log is intentionally kept separate from `store.py`. Audit logs should be append-only and never mutated. Mixing them with the mutable store would make that invariant harder to enforce.

## What's not done (would do next)

- **Persistence** — write audit entries to a time-series store (Tinybird or ClickHouse). Retention policy: 90 days standard, 1 year for enterprise customers.
- **Pagination** — `GET /v1/audits` returns all entries. At scale this needs cursor-based pagination.
- **Real actor identity** — once a real auth layer exists (RBAC, tenant mapping), replace the key prefix with a resolved `user_id` or `service_id`.
- **Chat completions logging** — inference requests are not audited here. A full request log (every inference call with tokens, latency, status) would live in a separate `request_log` table, not the audit log — different retention, different access pattern.
