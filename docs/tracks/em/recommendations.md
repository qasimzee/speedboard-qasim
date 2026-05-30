# Recommendations

## Headline

My first 90 days: harden the gateway layer. Right now it does format-only auth and basic routing. It should do more. Every request should be authenticated, attributed to a tenant and key, and stamped with per-layer latency. Prometheus metrics — 5xx rate, latency, rate limit hits — should feed a Grafana dashboard. Every mutating action should write an audit record. I've seen this pattern work at Stripe. Visa/MC traffic flowed through a PCI compliance layer that gave us clean attribution, audit, and failure isolation by design. Without that boundary, every incident is a guessing game. With it, observability, identity enforcement, and audit logging become one investment, not three separate projects.

## Top 3 risks at 10× platform load

### 1. No observability baseline — can't separate product failures from inference plane failures

At 10x load, latency spikes and error rates will increase. Without per-layer instrumentation, every incident becomes a guessing game — is it the gateway, the DB, or the inference engine? The architecture doc explicitly flags uneven instrumentation coverage.

**What I'd do:** Instrument the gateway layer first with Prometheus — 5xx rate, latency, and rate limit hits as the three baseline alerts. Add per-layer latency stamps to canonical logs (auth, key lookup, inference) so spikes can be attributed without digging through raw logs. Add a `request_id` correlation ID generated at the gateway and propagated through every downstream service — same pattern as Stripe's `action_id`. Build a Grafana dashboard on top. Buy SignalFx or Datadog initially for speed — migrate to self-hosted Prometheus when the bill justifies it. Ship structured logs to Splunk.

This directly mirrors what I built at Stripe for Issuing authorization reliability at ~1.5M requests/day. The key lesson: without layer-level latency attribution, you waste the first 30 minutes of every incident figuring out who owns it.

### 2. No authorization layer — tenant isolation is one missed filter away from a security incident

API keys are validated by format only. Scopes are stored but never enforced. There is no tenant mapping. A query missing a `WHERE account_id = ?` filter exposes one customer's data to another. At 10x customers, that's a security incident.

**What I'd do:**
- **Phase 1**: Enforce key → tenant mapping at the gateway. Every request resolves to a tenant before hitting any handler. Scope enforcement at the same layer — a key with `inference:read` cannot hit billing or admin endpoints. Return 403.
- **Phase 2**: RBAC — Account Admin, Developer, Analyst. Applied as middleware on every endpoint, not per-endpoint logic. Sign up creates a tenant entity with the first user as owner.
- **Migration**: Existing `psk-` keys get mapped to a default tenant on first use. No breaking change — they keep working, but now have a tenant context attached.

I shipped this at Reddit Ads — every endpoint had a function decorator ensuring the actor had permissions for that account. Roles: Super Admin, Account Admin, Creator, Analyst. Same pattern applies here.

### 3. No customer-facing observability — support load scales with traffic

Without customer-facing observability, every failed request becomes a support ticket. The architecture doc flags this as a repeated customer signal. At 10x, Account Managers can handle this manually. That doesn't last.

**What I'd do:**
- **Phase 1**: Email alert — time of outage, number of requests failed, affected key. Stops most support noise immediately.
- **Phase 2**: Request history dashboard in portal — status codes, error reasons, per key. Eventually consistent (few minutes lag) is acceptable here.
- **Phase 3**: Customer-defined alert thresholds — 5xx rate, rate limit hits, spend. Route to Slack, PagerDuty, or email via webhook.
- **Real-time signals**: Rate limit headers (`Retry-After`, `X-RateLimit-Remaining`) must be real-time. An agent hitting a limit needs to know now, not 5 minutes later.
- **Retry contracts**: Every error response needs a machine-readable signal — should the caller retry, wait, or stop? A 429 needs `Retry-After`. A 500 needs to distinguish transient (retry safe) from permanent (don't retry). Without this, agents retry blindly and amplify incidents.

I shipped a version of this at Stripe — exposed failed authorization data (STIPs) via API and portal, with automatic alerts when customer webhooks failed.

## Top 3 risks at 100× platform load

### 1. No request log — no real-time spend enforcement, no audit trail, no customer self-serve

At 100x request volume, daily usage aggregates break down completely. Completions are not stored anywhere today. Spend caps can't be enforced in real-time. Customers can't query their request history. There is no correlation ID tying events together across services. At 100x you can't hire enough Account Managers to handle customer issues manually — customers need to self-serve.

**What I'd do:**
- Build a `request_log` table — one row per event, linked by `request_id`. Fields: `request_id`, `account_id`, `api_key_id`, `model`, `event_type`, `input_tokens`, `output_tokens`, `spend_usd`, `status_code`, `latency_ms`, `error_type`, `created_at`.
- **Start**: Postgres — already in the stack, good enough at 10x.
- **100x**: Migrate to a managed time-series store — Tinybird or Axiom (ClickHouse under the hood). Buy, don't build. Migrate to self-hosted ClickHouse when the bill justifies it.
- Use Redis for real-time spend cap enforcement on the hot path — atomic increments per key, fast.
- Ship rows to Splunk for ops debugging. Expose summaries via portal API for customers.

At Stripe, every request had a single `action_id` traceable across all services and events. Same pattern here.

### 2. Billing and spend controls can't scale manually — agents breach caps before daily aggregates run

At 100x, manual invoicing and daily spend aggregates break down. A runaway agent can breach its spend cap before the next aggregate runs. Customers get surprise invoices. At Reddit Ads, large customers on contracts required manual outreach when they exhausted their ad budgets — not scalable. At Stripe, balance delays due to bank holidays caused declined transactions at scale.

**What I'd do:**
- **Buy**: Stripe Billing or Orb for usage-based metering and invoicing. Don't build this.
- **Build**: Real-time spend enforcement at the gateway using Redis atomic increments — core product behavior, not something a vendor does.
- **Proactive alerts**: Notify customers at 80% of spend cap, not 100%. Same lesson from Reddit — don't wait until they're out of budget. Model after Google Cloud billing alerts — customer-defined thresholds, email/Slack notifications.
- **Grace period**: Don't hard-cut customers at the limit. Give a grace window with escalating alerts before suspension.

### 3. DDoS and abuse detection can't be handled manually — agent traffic makes it worse

At 10x, abusive API keys can be manually identified and blocked. At 100x that's impossible. Agent traffic amplifies this — a single misbehaving agent can generate retry storms, infinite loops, and spend spikes in seconds, taking down the platform for everyone.

**What I'd do:**
- **Buy**: DDoS protection — AWS Shield or Cloudflare. Don't build this.
- **Buy**: Fraud/abuse detection baseline — ML-based pattern detection. At Stripe, manual vetting of Issuing accounts worked at 10x. At 100x a fraud detection algorithm was built to analyze transaction patterns and block malicious accounts in real-time. Same principle applies here.
- **Build**: Spend velocity alerts at the gateway — if a key spends $X in Y minutes, auto-suspend and alert the customer.
- **Build**: Circuit breakers at the gateway — if inference plane slows down, stop sending requests, return 503 with `Retry-After`. Prevents retry storms from amplifying incidents.
- **Build**: Agent-specific rate limits — tighter per-minute caps for keys showing agent-like patterns (high parallelism, repetitive requests).

## Customer mix

**1. Rate limiting**

For humans, a rate limit is a UX message — "slow down, try again." For services and agents it's a reliability contract. At Reddit Ads we built a rate limiter scoped by `account_id`. The same approach applies at Speedboat — per-key rate limits with machine-readable `429` responses and `Retry-After` headers. Agents need to know exactly when to retry, not just that they were blocked.

**2. Alerting**

For humans, alerting lives in the portal — a dashboard they check. For services and agents, alerting needs to be programmatic and proactive. At Reddit, internal alerts were enough at 10x because the team could intervene manually. At 100x, alerts went directly to customers via email. At Speedboat the same progression applies — start with Speedboat-sent emails, expand to customer-defined webhooks (Slack, PagerDuty) as scale grows.

**3. Authorization**

Humans authenticate via SSO (Okta, Google). At Reddit, operators and owners had separate roles enforced at every endpoint. For agents at Speedboat, SSO is irrelevant — they need scoped short-lived tokens with tighter permissions than a human admin. An agent should never carry the same full account access as an Account Admin.

## Build vs buy

| Capability | Build | Buy | Reason |
|---|---|---|---|
| Identity / SSO / SAML / SCIM (humans) | | Buy | WorkOS or Auth0. Don't build SSO from scratch — high complexity, low differentiation. |
| Workload / service / agent identity (non-humans) | Build | | Scoped keys, short-lived tokens — core product behavior. Vendors don't solve this for you. |
| Usage-based billing | | Buy | Stripe Billing or Orb. Metering and invoicing is complex. Seen the pain of doing this manually at Reddit and Stripe. |
| Customer-facing observability (request logs, usage charts) | Build | | Core product differentiator. Customers choose platforms they can debug themselves. |
| Internal observability (logs, metrics, traces, alerting) | | Buy initially | SignalFx or Datadog first — get metrics flowing in days. Migrate to Prometheus + Grafana when cost justifies it. |
| Audit logging (customer-facing) | Build | | Start with app-layer audit calls (`add_entry()` on each mutating endpoint). Migrate to CDC (Postgres logical replication + Debezium) in production — catches everything including direct DB queries and migrations that bypass the app layer. Built CDC at Reddit. |
| Secrets management | | Buy | AWS Secrets Manager or HashiCorp Vault. Solved problem. |
| API rate-limiting / spend-cap enforcement | Build | | Redis-based, core to the gateway. Can't outsource real-time spend enforcement. |
| Fraud / abuse detection | | Buy | AWS Shield for DDoS. ML-based fraud detection at 100x. Too complex to build from scratch. |
| Status page | | Buy | Statuspage.io or Instatus. Zero reason to build this. |
| Email / transactional comms | | Buy | SendGrid or Postmark. |

## Phased rollout

### First 30 days

- **Listen tour**: Engineering team, Account Managers, 5-10 customers. Understand what's actually breaking before changing anything.
- **Quick win**: Prometheus/SignalFx metrics + Grafana dashboard — 5xx rate, latency, rate limit hits. Internal ops can see what's breaking for the first time.
- **Freeze**: New feature work until observability baseline is in place.

### 30–90 days

- Enforce key → tenant mapping at the gateway. Every request resolves to a tenant before hitting any handler.
- Scope enforcement at the gateway — a key with `inference:read` cannot hit billing or admin endpoints. Return 403.
- Request log table with `request_id` correlation ID propagated across all services.
- Basic RBAC — Account Admin, Developer, Analyst. Applied as middleware, not per-endpoint logic.

### 90–180 days

- Customer email alerts — spend threshold (80%), error rate spikes, outage notifications.
- Request history dashboard in portal — per key, filterable by status code and error type.
- Stripe Billing or Orb integration for usage-based invoicing.
- Redis-based real-time spend cap enforcement at the gateway.
- Migrate audit logging from app-layer (`add_entry()`) to CDC — Postgres logical replication + Debezium. Guarantees no mutation is missed, including direct DB queries, migrations, and admin tooling that bypasses the application layer.

### Explicitly deferred

- SSO/SCIM — buy WorkOS but implement after RBAC foundation is solid. No point adding SSO before you have roles to assign.
- Customer-defined webhooks (Slack, PagerDuty) — after email alerts are working and validated.
- Fraud/abuse detection — needs request log data first. Can't detect patterns without history.
- Customer-facing request log API — portal dashboard ships first, programmatic API after.

## Lived-experience appendix

| Recommendation | Lived / Proposed | Context (if Lived) or de-risk plan (if Proposed) |
|---|---|---|
| Internal observability — Grafana + Prometheus/SignalFx, Splunk for logs | Lived | Built at Stripe for Issuing authorization reliability (~1.5M req/day). Used Redshift + Splunk. Per-layer latency attribution separated our failures from Visa/MC failures. Would use Grafana + Prometheus instead of Splunk next time. |
| Correlation ID (`request_id`) propagated across all services | Lived | At Stripe every request had a single `action_id` traceable across all services and events. |
| Customer-facing observability — email alerts, request history dashboard | Lived | Built at Stripe for Issuing — exposed failed authorization data (STIPs) via API and portal. Automatic alerts when customer webhooks failed. |
| RBAC — Account Admin, Developer, Analyst | Lived | Built at Reddit Ads — Super Admin, Account Admin, Creator, Analyst roles. Enforced as a function decorator on every endpoint, not per-endpoint logic. |
| Rate limiting scoped by account | Lived | Built at Reddit Ads — rate limiter scoped by `account_id`. |
| Audit logging — app-layer first, CDC in production | Lived | App-layer audit wiring (`add_entry()` on each mutating endpoint) built for this code slice. CDC (Postgres logical replication + Debezium) built at Reddit — guarantees no mutation is missed, including direct DB queries and admin operations that bypass the app. |
| Fraud / abuse detection | Lived (observed) | At Stripe, manual vetting of Issuing accounts at 10x. At 100x a fraud detection algorithm was built using ML to detect malicious patterns in real-time. Observed but did not personally ship. |
| Usage-based billing — buy Stripe Billing / Orb | Proposed | Seen the pain at Reddit Ads (manual contracts) and Stripe (balance delays). De-risk: evaluate Orb and Stripe Billing in first 30 days, run a proof of concept against the mock. |
| Redis-based real-time spend cap enforcement | Proposed | Logical extension of rate limiting experience at Reddit Ads. De-risk: prototype Redis atomic increments against the gateway in first 30 days. |
| DDoS protection — buy AWS Shield / Cloudflare | Proposed | Aware of AWS-based fraud detection at Stripe but didn't personally build it. De-risk: engage AWS Shield team in first 30 days. |
| Time-series request log — Tinybird / ClickHouse | Proposed | Pattern informed by Redshift experience at Stripe. De-risk: evaluate Tinybird against request volume projections before committing. |

## What I'd want before committing to any of this

- Current request volume and growth rate — are we actually at 10x risk or further away?
- Existing instrumentation — what's already logged, what's dark?
- Current support ticket breakdown — what are customers actually complaining about?
- Existing vendor contracts — what are we already paying for (Datadog, Splunk, etc.)?
- Engineering team size and structure — who owns what today?

## Open questions you'd ask the team

- What does the on-call rotation look like today — who gets paged when the platform is down?
- Has there ever been a cross-tenant data leak or security incident? How was it handled?
- How are enterprise customers being onboarded today — is it fully manual?
- What's the current support ticket volume and who handles it?
- Are there any known agent customers today — and have we seen retry storms or spend spikes from them?
- What's the relationship with the inference platform team — how do we coordinate on incidents?
