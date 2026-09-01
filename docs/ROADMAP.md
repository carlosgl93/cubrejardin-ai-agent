# Roadmap

**Status:** living document · **Owner:** Carlos · **Last update:** 2026-08-18

## Vision

Vertical SaaS chatbot platform. First customer: CubreJardin (Chile, ecommerce). Each new channel is a feature for existing verticals, not a separate product. Channels live behind per-tenant opt-in flags.

## Channel order

| # | Channel | Status | Rationale |
|---|---|---|---|
| 1 | **WhatsApp** | Shipped · in prod | First customer, paying, real traffic |
| 2 | **Instagram** | ~80% code-complete, gated on Meta approval | Closest to GA; existing OAuth + adapter + token cron |
| 3 | **Facebook Messenger** | Stub only (webhook + OAuth exchange exist, untested) | Submit with IG in one Meta app to halve approval wait |
| 4 | **Telegram** | Webhook code exists, never shipped | Defer to end-of-line; only build if a tenant asks |
| — | **TikTok** | **DEFERRED** — see below | Gated API access, no public registration |

## Instagram GA criteria

A channel is "GA" when all 5 are true:

1. **Real traffic** — CubreJardin live with inbound DMs (not test traffic)
2. **Token refresh** verified across ≥7 days with zero manual intervention
3. **Failure modes handled** — token revoked mid-convo, Meta 5xx, rate limits, missing media
4. **Onboarding doc** — 1-pager: how to flip IG on for a tenant
5. **Customer-comms plan** — SLA, escalation path, who pays when Meta charges per-message

**Cut from GA bar:** observability/alerts. Defer to channel 2 — instrument once, copy pattern.

## Critical path

**Meta Business + App approval is the bottleneck, not code.** IG and FB Messenger permissions can be requested in **one** Meta app submission. While Meta reviews (1–4 weeks typical):

- Finish FB Messenger code so it flips on the same day IG does
- Write the 1-pager IG onboarding doc
- Cut scope: see below

## Meta submission status (as of 2026-08-18)

**Already unblocked:**

- SG CLOUD SpA Business Manager **verified** ✓
- App `Agents-Whtsapp` (`1082408593965616`) exists, owned by SG CLOUD SpA
- Admin team in place: Carlos, Benjamín, 2 system users

**Remaining work to flip IG + Messenger live:**

1. Add payment method (Meta charges per-message on IG too)
2. Add **Instagram product** to `Agents-Whtsapp` app
3. Add **Messenger product** to same app
4. Connect CubreJardin's IG Professional account + FB Page via OAuth
5. Request 3 IG permissions + 2 Messenger permissions
6. **Single App Review submission** covering both permission sets
7. Webhook URLs configured per product

**Realistic timeline:** 1–2 weeks from submission to live (3–7 day App Review once verified). Business Verification wait is **skipped** — already done.

**Decision logged:** Extend `Agents-Whtsapp` with IG + Messenger products rather than creating separate apps. One app, one review submission, existing admin team carries over.

Detailed test-instructions template: see `FB_APP_REVIEW_GUIDE.md` (Instagram + Messenger addenda appended).

## Scope cuts (deferred, not deleted)

These exist in the working tree but are **not** blocking IG GA:

- `services/telemetry.py` — defer until channel 2
- `services/message_queue.py` — defer until channel 2
- `services/interactive_service.py` — defer until channel 2
- One-shot migration endpoint (revert chain) — premature infra, document as future need
- Unmerged branches (`ops-postgres-hardening`, `rag-pgvector-review`, `sg-cloud-phase0`) — each is its own deliverable, don't bundle

## Multi-tenant architecture

Already in place (`tenant_id` filters everywhere). Justified because:
- Future vertical #2 needs it (no signed LOI yet, but design cost is sunk)
- Per-channel opt-in flags (`instagram_connected` already exposed on `/tenants/me`) prevent forced migrations

**Risk:** if CubreJardin configs become THE config (not A config), the multi-tenant plumbing pays no rent. Refactor trigger: when vertical #2 signs.

## Open questions

- **Vertical #2** — none signed. Roadmap priority follows real pipeline, not vibes.
- **Pricing model** — TBD. Per-tenant subscription vs per-conversation vs retainer. CubreJardin may be on a project fee today.
- **TikTok** — see deferral log.

## Deferral log

### TikTok (2026-08-18)

**Decision:** Dropped from active roadmap.

**Rationale:**
- TikTok messaging API for third-party bot builders is gated / invite-only as of 2026
- No public app registration flow like Meta
- CubreJardin has no current TikTok DM volume to justify pre-emptive build

**Revisit when:**
- CubreJardin shows real TikTok DM traffic they want to deflect
- TikTok opens public messaging API registration
- Carlos establishes a TikTok partner contact

**Do not** design around this door until one of the above is true.
