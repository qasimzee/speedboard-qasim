"""Smoke test for the audit log code slice.

Requires the mock server to be running at http://localhost:3001.
Run with: python3 code-slice/smoke_test.py

Tests:
- POST /v1/api-keys writes an audit entry (api_key.created)
- DELETE /v1/api-keys/:id writes an audit entry (api_key.revoked)
- POST /v1/deployments writes an audit entry (deployment.created)
- GET /v1/audits returns all entries
- GET /v1/audits?action=... filters correctly
- GET /v1/audits?actor=... filters correctly
"""
import sys
import urllib.request
import urllib.error
import json

BASE = "http://localhost:3001"
TOKEN = "psk-mock-mockkey"
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}


def request(method, path, body=None):
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(f"{BASE}{path}", data=data, headers=HEADERS, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print(f"FAIL {method} {path} -> HTTP {e.code}: {e.read().decode()}")
        sys.exit(1)


def assert_eq(label, actual, expected):
    if actual != expected:
        print(f"FAIL {label}: expected {expected!r}, got {actual!r}")
        sys.exit(1)
    print(f"  ok  {label}")


def assert_in(label, value, collection):
    if value not in collection:
        print(f"FAIL {label}: {value!r} not in {collection!r}")
        sys.exit(1)
    print(f"  ok  {label}")


print("=== Audit log smoke test ===\n")

# 1. Create an API key
print("1. Create API key")
key = request("POST", "/v1/api-keys", {"name": "smoke-test-key", "scopes": ["inference:read"]})
key_id = key["id"]
assert_in("key id present", "key_", key_id)
print(f"     created {key_id}")

# 2. Revoke the key
print("2. Revoke API key")
request("DELETE", f"/v1/api-keys/{key_id}")

# 3. Create a deployment
print("3. Create deployment")
dep = request("POST", "/v1/deployments", {
    "name": "smoke-test-dep",
    "model_source": "meta-llama/Meta-Llama-3.1-8B-Instruct",
    "gpu_type": "a10g",
    "replicas": 1,
})
dep_id = dep["id"]
print(f"     created {dep_id}")

# 4. Query full audit log — expect at least 3 entries from this run
print("4. GET /v1/audits")
audits = request("GET", "/v1/audits")
actions = [e["action"] for e in audits["data"]]
assert_in("api_key.created in log", "api_key.created", actions)
assert_in("api_key.revoked in log", "api_key.revoked", actions)
assert_in("deployment.created in log", "deployment.created", actions)

# 5. Filter by action
print("5. Filter by action=api_key.revoked")
filtered = request("GET", f"/v1/audits?action=api_key.revoked")
assert_eq("all results match action",
    all(e["action"] == "api_key.revoked" for e in filtered["data"]), True)
assert_eq("revoked key id present",
    any(e["resource_id"] == key_id for e in filtered["data"]), True)

# 6. Filter by actor
print("6. Filter by actor=psk-mock-")
by_actor = request("GET", "/v1/audits?actor=psk-mock-")
assert_eq("all results match actor",
    all(e["actor"] == "psk-mock-" for e in by_actor["data"]), True)

# 7. Verify before/after shape on revoke entry
print("7. Verify before/after on api_key.revoked entry")
revoke_entry = next(
    (e for e in audits["data"] if e["action"] == "api_key.revoked" and e["resource_id"] == key_id),
    None
)
if not revoke_entry:
    print("FAIL: could not find revoke entry for created key")
    sys.exit(1)
assert_eq("before.revoked_at is null", revoke_entry["before"]["revoked_at"], None)
assert_eq("after.revoked_at is set", revoke_entry["after"]["revoked_at"] is not None, True)
assert_eq("ip present", isinstance(revoke_entry["ip"], str), True)
assert_eq("user_agent present", isinstance(revoke_entry["user_agent"], str), True)

print("\n=== All checks passed ===")
