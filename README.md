# SentinelPay v4.2

Phases 1-7 provide the auth/database foundation, machine-readable merchant catalog, bounded buyer mandates, the deterministic SecurityKernel, Razorpay Test Mode checkout, bounded negotiation, permissioned basket growth, and bounded campaigns.

## Prerequisites

Python 3.11+, Node 20+, and a Supabase project. Use Razorpay Test Mode only in later phases.

## Configure Supabase

1. Create a Supabase project and enable Email auth.
2. Copy `.env.example` to `backend/.env` and fill the Supabase values. `SUPABASE_SERVER_SECRET` is backend-only; use a service-role secret only on the server.
3. Copy `frontend/web/.env.example` to `frontend/web/.env.local`. Populate only `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, and the backend URL.
4. Never expose server secrets, Razorpay secrets, refresh tokens, cookies, passwords, CVV, or UPI PINs in the frontend.

## Run

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --reload
```

```powershell
cd frontend/web
npm install
npm run dev
```

Open `http://localhost:3000/login`. Create an account, then log in. The app redirects unauthenticated users from `/app` to `/login`.

## Verify

```powershell
cd backend; pytest; ruff check app tests
cd frontend/web; npm run typecheck; npm run lint; npm run build
```

`GET /health` always checks application liveness. `GET /ready` checks the configured database connection. `GET /api/me` requires a valid Supabase access token. Database SQL is managed by Alembic in `backend/migrations`; no dashboard schema edits are required.

RLS policy behavior is documented in `database/rls/phase-1-policies.md`. `database/seeds/dev.sql` provides deterministic Phase 2 commerce data after its user UUID is mapped to a real Supabase Auth user.

## Phase 2 demo: prove the merchant is agent-readable

After applying migrations, replace `demo_user_id` in `database/seeds/dev.sql` with an existing Supabase Auth user UUID and run:

```powershell
psql $env:SUPABASE_DATABASE_URL -f ..\database\seeds\dev.sql
```

Authenticate in the UI and open `http://localhost:3000/merchant`. The Agent-Readable Preview calls `GET /api/merchants/{merchant_id}/catalog`. A public tool consumer can use:

```bash
curl -X POST http://localhost:8000/api/agent/catalog/search -H "Content-Type: application/json" -d '{"query":"Sony headphones"}'
curl http://localhost:8000/api/agent/products/20000000-0000-0000-0000-000000000001
curl http://localhost:8000/api/agent/products/20000000-0000-0000-0000-000000000001/inventory
curl http://localhost:8000/api/agent/products/20000000-0000-0000-0000-000000000001/offers
```

Responses are built from PostgreSQL product, variant, inventory, relationship, and active-policy records. Private price-floor fields are not in agent DTOs.

## Phase 3 trace

Open `http://localhost:3000/buyer` and submit: `Buy premium Sony headphones under Rs 25,000, new only. Ask me before payment.` The trace is:

```text
USER_INPUT raw message
  -> ParsedIntent proposal (SYSTEM_DERIVED, budget preserved)
  -> explicit user confirmation
  -> ACTIVE immutable mandate + nonce + SHA-256 integrity hash
  -> BuyerAgent calls MerchantAgent.catalog_search
  -> product cards sourced from MERCHANT_CATALOG
```

If budget is absent, the API returns `REQUIRES_CLARIFICATION`. Intent and conversation APIs use the task-aware `ModelGateway`; deterministic tests use the mock adapter. Model-derived intent remains a proposal and the service preserves user-derived budget, quantity, conditions, permissions, and `auto_purchase_allowed=false` until visible confirmation.

Model routing is backend-only:

- Normal chat, intent parsing, negotiation, and campaign copy: Groq `openai/gpt-oss-20b`, then NVIDIA Lightning, then fail closed.
- Complex campaign reasoning and long context: NVIDIA `nvidia/nemotron-3.5-lightning-30b-a3b`, then Groq `openai/gpt-oss-120b`, then fail closed.
- Very complex reasoning: Groq `openai/gpt-oss-120b`, then NVIDIA `nvidia/nemotron-3-ultra-550b-a55b`, then fail closed.
- Red-team generation starts with NVIDIA so it uses a provider different from the normal primary.

Every route validates structured output and fails closed when all configured providers fail. Provider keys must exist only in `backend/.env` or the deployment platform's server-side secret store; never expose them as `NEXT_PUBLIC_*` values.

## Phase 9 security evidence

Authenticated users can open `/judge` to run 16 controlled buyer, merchant, campaign, payment, and prompt-injection attacks. Evidence is persisted in `red_team_runs` and `red_team_attacks`; each attack shows policy results, Z3 assertions, SecurityKernel outcome, whether Razorpay was called, and its append-only audit event.

Independent evidence endpoints are available at `/verify/transaction/{id}`, `/verify/mandate/{id}`, `/verify/audit/{id}`, and `/verify/provenance/{id}`. See [the Phase 9 judge demo](docs/phase9-judge-demo.md) for the five-minute sequence.

## Phase 10 advanced lab

The authenticated `/advanced` interface uses Framer Motion and exposes six isolated advanced evaluations. Every flag defaults OFF and every evaluation records safe input, result, baseline, metrics, provenance, and a hash-chained audit event. See [Phase 10 advanced extensions](docs/phase10-advanced-extensions.md) for claims, measurements, fallbacks, and maturity.

## Phase 4 verification

Create a cart with `POST /api/carts`, add one real DB product with `POST /api/carts/{id}/items`, then call `POST /api/checkout/prepare` with a unique `idempotency_key`. The SecurityKernel evaluates buyer, merchant, inventory, mandate, and currency constraints in one Z3 solver. With `auto_purchase_allowed=false`, a SAT cart returns `REQUIRE_APPROVAL`; `POST /api/checkout/{transaction_id}/confirm` verifies the cart commitment and returns `ALLOW` without creating payment.

Safety matrix covered by automated tests:

| Cart | Expected result |
| --- | --- |
| XM4, INR 19,999, qty 1, valid mandate | SAT / REQUIRE_APPROVAL |
| Total above INR 25,000 buyer budget | UNSAT / BUYER_BUDGET |
| Total below INR 18,500 merchant floor | UNSAT / MERCHANT_FLOOR |
| Discount above policy maximum | UNSAT / MERCHANT_DISCOUNT |
| Quantity above available stock | UNSAT / INVENTORY |
| USED item when mandate allows NEW only | UNSAT / BUYER_CONDITION |

PaymentService and Razorpay order creation begin in Phase 5 only.

## Phase 5: Razorpay Test Mode

Add only Test Mode credentials to `backend/.env`:

```dotenv
RAZORPAY_TEST_KEY_ID=rzp_test_...
RAZORPAY_TEST_KEY_SECRET=...
RAZORPAY_WEBHOOK_SECRET=...
```

The secrets stay in FastAPI. The browser receives only the public Test key ID, order ID, exact verified amount/currency, and payment-attempt ID.

```powershell
cd backend
alembic upgrade head
uvicorn app.main:app --reload
```

```powershell
cd frontend/web
npm run dev
```

For local webhook testing, expose port 8000 with a tunnel of your choice and configure this Test Mode webhook URL in the Razorpay Dashboard:

```text
https://YOUR-TUNNEL.example/api/webhooks/razorpay
```

Subscribe to `payment.captured`, `payment.failed`, and `order.paid`. Use the exact same webhook secret in `backend/.env`; tunnel infrastructure is not hard-coded.

Manual successful trace:

1. Open `/buyer`, start a conversation, submit the Sony request, and confirm the mandate.
2. Press **Verify & Pay** on the DB-backed candidate.
3. Confirm SecurityKernel SAT, explicit approval, and the Razorpay Test Checkout overlay.
4. Complete checkout using an instrument documented by Razorpay for Test Mode.
5. Confirm the UI remains verification-pending until backend verification or a signed webhook produces `CAPTURED`.
6. Confirm `payment_attempts.status=CAPTURED`, `transactions.status=SUCCESS`, the mandate is consumed once, and the agent session is converted.

Ambiguous trace:

```text
provider timeout/callback uncertainty -> UNKNOWN -> no new order -> reconcile existing provider order -> PAYMENT_PENDING/CAPTURED/FAILED
```

Never provide a real UPI PIN, CVV, bank password, card credential, session cookie, or Razorpay live-mode key.

## Phase 6: bounded negotiation and basket growth

The buyer-facing API never accepts a MerchantAgent-authored numeric turn. `POST /api/negotiations/{id}/step` accepts a confirmed buyer offer, while the backend deterministic controller owns the merchant floor, counter amount, expiry, maximum rounds, fallback selection, and acceptance. Model metadata and wording are auditable but cannot authorize a price.

Use the buyer demo request:

```text
Negotiate for premium Sony headphones under Rs 25,000, new only, up to 2 items. Offer me an accessory cross-sell. Ask me before payment.
```

After activating the mandate, build the shared cart on `/buyer`.

1. **Success:** Start negotiation, submit a bounded offer, respond to the public counter, and apply the accepted price. The UI reports the full SecurityKernel recommit result.
2. **Fallback:** Let the bounded rounds finish without overlap acceptance. If the locked fallback remains valid and better, the session ends `FALLBACK`; apply it to the same cart and re-verify.
3. **Cross-sell:** Load mandate-safe offers, explicitly accept the Protective Case, and confirm `SecurityKernel: REQUIRE_APPROVAL`. Nothing is auto-added.

Phase 6 APIs:

```text
POST /api/negotiations
POST /api/negotiations/{id}/step
GET  /api/negotiations/{id}
POST /api/negotiations/{id}/apply-to-cart
POST /api/growth/recommendations
POST /api/growth/{upsell|cross_sell}/{event_id}/accept
```

Negotiated or expanded carts are not allowed to bypass checkout. Every modification reruns buyer, merchant, inventory, currency, mandate-integrity, and per-line constraints in the existing one-call Z3 path before the Phase 5 payment flow can continue.

## Phase 7: campaign MVP

Open `http://localhost:3000/merchant/campaigns`, enter a merchant UUID, and run a manual opportunity scan. The detector queries PostgreSQL inventory, product activity, carts, transactions, agent sessions, commercial policy margin room, and accepted growth events. Scores, reasons, and exact input metrics are stored in `campaign_opportunities`; configurable weights use the `CAMPAIGN_WEIGHT_*` environment variables.

Campaign flow:

```text
actual DB signals -> stored opportunity -> PROPOSED campaign
-> explicit OWNER/ADMIN approval -> SCHEDULED/ACTIVE
-> deterministic buyer/cart eligibility -> immutable offer snapshot
-> offer applied -> existing SecurityKernel single Z3 solver
-> explicit checkout confirmation -> atomic campaign reservation
-> Razorpay Test capture -> campaign redemption and revenue event
```

The in-process prototype scheduler runs every `CAMPAIGN_SCAN_INTERVAL_MINUTES` and activates approved schedules or stops campaigns at time, budget, redemption, or inventory limits. Production deployment should run the same `CampaignOrchestrator.run_cycle` from a durable single-owner worker with distributed locking.

Campaign expiry failure:

```text
offer applied -> campaign expires -> POST /api/checkout/prepare
-> CAMPAIGN_NOT_EXPIRED is UNSAT in the unified evaluation
-> transaction DENIED -> stale discount removed
-> cart marked campaign_reconfirmation_required=true
-> no Razorpay order -> buyer must review and confirm a freshly priced cart
```

Campaign APIs:

```text
POST /api/merchants/{id}/campaign-opportunities/scan
POST /api/merchants/{id}/campaign-signals
GET  /api/merchants/{id}/campaign-opportunities
POST /api/merchants/{id}/campaigns
POST /api/merchants/{id}/campaigns/{campaign_id}/approve
GET  /api/merchants/{id}/campaigns
POST /api/merchants/{id}/campaigns/{campaign_id}/{pause|stop}
POST /api/campaign-offers/eligible
POST /api/campaign-offers/{offer_id}/apply
```

## Phase 8: honest revenue attribution

Open `http://localhost:3000/merchant/analytics`. REAL metrics are computed only from stored events and transactions with both `transactions.status='SUCCESS'` and `payment_attempts.status='CAPTURED'`. Failed, denied, pending, unknown, and SIMULATED records are excluded from real revenue.

Stable campaign assignment:

```text
bucket = first_8_bytes(SHA256(mandate_id + ":" + campaign_id)) % 100
CONTROL   when experiment enabled and bucket < control_percentage
TREATMENT otherwise
```

The default split is 20% CONTROL and 80% TREATMENT. Assignments have a unique `(campaign_id, mandate_id)` boundary, so refreshing eligibility cannot rerandomize a buyer. CONTROL assignments are stored but receive no campaign offer.

Formulas:

```text
Control CR = Control Conversions / Control Sessions
Treatment CR = Treatment Conversions / Treatment Sessions
CR Lift = Treatment CR - Control CR
Revenue Per Session = Captured Revenue / Eligible Sessions
Incremental Revenue Estimate = (Treatment RPS - Control RPS) * Treatment Sessions
Control AOV = Control Captured Revenue / Control Conversions
Treatment AOV = Treatment Captured Revenue / Treatment Conversions
AOV Lift = Treatment AOV - Control AOV
Revenue Per Discount Rupee = Controlled Estimate / Discount Cost
```

When both groups exist, the UI labels the result `CONTROLLED EXPERIMENT ESTIMATE`. Without a valid control group, it displays only `ATTRIBUTED CAMPAIGN REVENUE` and never calls it causal lift. Zero denominators produce zero rates, not errors or invented values.

Source tables:

```text
agent_sessions, carts, transactions, payment_attempts,
campaign_assignments, campaign_offers, campaign_redemptions,
upsell_events, cross_sell_events, negotiation_sessions, campaign_events
```

Synthetic evaluation uses `simulated_commerce_sessions` with mandatory `SIMULATED` provenance. The generator accepts 100-1000 sessions, uses deterministic UUIDs and seed-based outcomes, and never creates Razorpay payment attempts or enters REAL metrics.

Phase 8 APIs:

```text
POST /api/merchants/{id}/analytics/refresh
GET  /api/merchants/{id}/analytics?data_scope=REAL|SIMULATED
POST /api/merchants/{id}/analytics/simulate
```

Captured Razorpay Test Mode payments support idempotent partial/full refund requests, cumulative refund limits, provider-state reconciliation, and audit events. Revenue dashboards must subtract only `PROCESSED` refunds when refund-adjusted net revenue is displayed.
