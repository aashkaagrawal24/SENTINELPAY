# Phase 10 Advanced Extensions

> Historical design note. The default-off research scope in this document was superseded by migration `0011_complete_advanced_stack` and `docs/complete-advanced-stack.md`.

Every extension is isolated, authenticated, provenance-tagged, audit-recorded, unable to import or call `PaymentService`, and disabled by default. Enabling an extension adds evidence or strategy proposals only. SecurityKernel, the unified Z3 transaction evaluation, human confirmation, and trusted Razorpay verification remain mandatory.

## A. External Market Intelligence

- Problem: provide buyer-side offer benchmarks without claiming universal third-party checkout.
- Architecture: `ExternalConnector` protocol with explicit capability; the included connector accepts evaluation snapshots only and always ends unsupported purchase in `HANDOFF`.
- Data: caller-supplied evaluation snapshots marked `SIMULATED`. No marketplace passwords, OTPs, sessions, or raw credentials are stored.
- Metrics: token-match precision, offer freshness, connector success rate, latency.
- Failure: empty result plus `HANDOFF`; SentinelPay never creates Razorpay payment for an external seller.
- Readiness: evaluation-only. No live official marketplace connector is configured.

## B. Contextual Bandit

- Problem: choose a negotiation posture without changing buyer ceiling, merchant floor, quantity, or campaign limits.
- Architecture: per-context UCB action selection across `AGGRESSIVE`, `BALANCED`, and `FAST_CLOSE`; persisted stats are isolated by merchant/context/action.
- Reward: buyer savings + merchant contribution - alpha*time - beta*failure - discount cost.
- Baseline: static `BALANCED`.
- Failure: deterministic `BALANCED` fallback.
- Measured evaluation: unexplored `BALANCED` selected in the deterministic fixture; authority changes were `{}`.
- Readiness: demo-ready for strategy selection, not autonomous authority.

## C. Budget Sufficiency Range Proof

- Narrow statement: a committed private budget is at least a public price.
- Construction: Pedersen commitment in the RFC 3526 group, a 32-bit decomposition of `budget - price`, Schnorr OR proofs that every committed bit is 0 or 1, and Fiat-Shamir challenges. The relation between the bit commitments and `BudgetCommitment / g^PublicPrice` is verified.
- Private input: budget and commitment blinding. The private budget is neither returned nor stored.
- Public inputs: price, budget commitment, proof.
- Standard authority: unchanged. The mandate and SecurityKernel budget assertion remain authoritative.
- Failure: invalid/tampered/insufficient proof returns false or denies proof generation; checkout receives no authority.
- Measured local evaluation: generation about 8.3 seconds, verification about 8.3 seconds, proof about 142 KB.
- Readiness: research-only and unaudited. This is not a claim that full SentinelPay policy executes in zero knowledge.

## D. Multi-Verifier Approval

- Problem: add independent review evidence for selected high-value transactions.
- Architecture: Ed25519 signed attestations over canonical payload hash, verifier identity, decision, issuance, and expiry; distinct k-of-n approvals are required and any verified denial blocks.
- Baseline: one verifier.
- Failure: bad signature, wrong payload, expiry, timeout, or insufficient quorum returns `DENIED`.
- Standard authority: `security_kernel_still_required=true`; approval cannot create a payment.
- Readiness: demo-ready as multi-verifier approval. It is not described as distributed consensus.

## E. B2B Procurement

- Problem: fill required quantity from approved vendors under budget and delivery deadline.
- Architecture: RFQ, supplier quote, and allocation tables plus Z3 Optimize allocation.
- Objective: cost + delivery penalty + vendor-risk penalty.
- Hard constraints: approved vendor, quantity, availability, supplier minimum quantity, budget, deadline.
- Baseline: cheapest single approved supplier.
- Failure: `NO_FEASIBLE_ALLOCATION`; no partial or payment action is silently created.
- Measured fixture: 100% fill rate, deadline compliance 100%, cost 820,000 minor units.
- Readiness: optimizer demo-ready. Multi-supplier payment settlement is not claimed.

## F. Negotiation Simulator

- Problem: compare repeated bargaining strategies without putting experimentation in checkout.
- Architecture: deterministic seeded hidden seller floors and buyer ceilings; compares candidate strategy against `FAST_CLOSE`.
- Metrics: reward lift, agreement rate, average rounds.
- Measured fixture: 500 episodes, `BALANCED` reward lift 1020.194, agreement rate 0.666.
- Failure: deterministic baseline remains available; no result reaches the core transaction path.
- Readiness: research-only. This implementation is an advanced simulator, not CFR.

## Feature Flags

```env
FEATURE_EXTERNAL_MARKET_INTELLIGENCE=false
FEATURE_CONTEXTUAL_BANDIT=false
FEATURE_ZK_BUDGET_SUFFICIENCY=false
FEATURE_MULTI_VERIFIER=false
FEATURE_B2B_PROCUREMENT=false
FEATURE_NEGOTIATION_SIMULATOR=false
```

The authenticated `/advanced` page displays server-side flag state and maturity. Disabled evaluation routes return 404 with an explicit statement that core behavior is unchanged.
