# NOTES

## Total time spent

~4–5 hours, split:

- Reading [ARCHITECTURE.md](ARCHITECTURE.md) and orienting: 1–2 hrs
- Recommendations doc: 1 hr
- Optional code slice: 20 min
- Reflection / write-up: 2 hrs

## Optional code slice

Slice C — audit log. Start at `backend/mock-server/audit_log.py`, then `routes/audits.py`. I chose it because it's the most direct expression of my headline recommendation: make the gateway layer the enforcement and observability boundary. The audit log is the first concrete output of that boundary.

## Stack used for the code slice

Python / FastAPI — same stack as the mock. No new dependencies added.

## AI tools used

Claude Code — heavily used for structuring the recommendations doc and writing the code slice implementation.

**Where I drove the content:**
- All lived experience — Stripe Issuing authorization, Reddit Ads RBAC and rate limiting, the Visa/MC PCI compliance layer analogy, Reddit Ads manual contract pain, Stripe balance delays
- All prioritization decisions — which risks matter at 10x vs 100x, what to defer, what to buy vs build
- The phasing logic — why observability before authorization, why SSO gets deferred
- Suggested adding a smoke test for the code slice — not in the brief, my call
- Suggested CDC (Postgres logical replication + Debezium) as the production end state for audit logging, based on what I built at Reddit — Claude implemented it but the idea and the context were mine

**Where I accepted AI output:**
- Paragraph structure and wording in the recommendations doc — Claude drafted from my answers, I reviewed and corrected
- The code slice implementation — Claude wrote the Python, I reviewed the design decisions (append-only separation from store, thread lock, actor extraction from the auth header)

**Where I rewrote AI output:**
- Sentence length and style throughout the recommendations doc — Claude's first drafts were too long. I asked for shorter, simpler sentences throughout.
- The actor extraction logic — Claude's first approach used a regex; I preferred the simpler `split("-", 2)` approach.

## The three things from my recommendations I most want to discuss

1. **Observability** — I built this at Stripe for Issuing authorization at ~1.5M req/day. The per-layer latency attribution pattern (equivalent of Stripe's `action_id`) is something I've seen save 30+ minutes on every incident. Want to walk through how we separated inference-plane failures from product-layer failures.

2. **Authorization** — I shipped RBAC at Reddit Ads. The function-decorator pattern (enforced at every endpoint, not per-handler) is a specific design choice I'd make again and want to defend. Also want to discuss the migration path for existing `psk-` keys.

3. **Customer signals** — specifically the observability-to-support-ticket relationship. I've seen this from both sides: at Stripe we shipped customer-facing failed authorization data (STIPs) that directly cut support load. At Reddit Ads, large customer contract management was manual and painful at scale. These shaped my phasing decisions — email alerts before dashboards, dashboards before APIs.

## What I'd ask for in my first 30 days

If I got the seat:

- **First 1:1 I'd book**: Engineering lead — to understand the current codebase, team structure, and what's already on the roadmap before I form strong opinions.
- **Second**: Account Manager — to hear what customers are actually complaining about, not what we think they're complaining about.
- **Third**: A customer call — to hear failure modes directly.
- **Metric I'd want a dashboard for**: Availability / uptime first — then as many sub-metrics as I can get (5xx rate by layer, latency p50/p99, rate limit hits). Once those are in place, top-level customer metrics (support ticket volume, spend per customer, active key count).
- **Conversation I'd schedule with another team**: Infrastructure / inference platform team — to understand the architecture deeper and establish how we separate their incidents from ours.
- **Thing I'd say "not yet" to**: SSO — it's the right call eventually but not before we have a real identity model and RBAC foundation in place. Also "not yet" to any full rewrite — you learn more by instrumenting what's there than by replacing it.

## Where I think this take-home is unfair, if anywhere

The lived-experience appendix is the most valuable part of this format — and also the hardest to fake. That's a feature, not a bug. The only tension is that candidates with breadth across many companies have more tags to draw from than candidates who went deep at one or two. But the format handles that — "Proposed + here's how I'd de-risk" is a legitimate answer.

## Feedback on the take-home

The ARCHITECTURE.md case study is well-constructed. The intentional gaps are real gaps — not invented problems. The three-customer-type framing (humans / services / agents) is the sharpest part: it forces you to think about the platform differently than a standard SaaS product. The code slice options are well-scoped — narrow enough to ship in an hour, meaningful enough to generate a real conversation.

One thing that would help: a rough sense of current scale (requests/day, customer count, team size). The 10x / 100x framing is useful but the starting point matters for calibrating which risks are urgent vs theoretical.
