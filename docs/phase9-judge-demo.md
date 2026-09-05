# Phase 9 Judge Demo

## Five-minute sequence

1. Sign in and open `/judge` from **Break SentinelPay**.
2. Run `buyer_budget_escalation`. Show `BUYER_BUDGET`, `UNSAT`, `DENY`, `Razorpay called: NO`, and the audit event ID.
3. Run `prompt_injection_catalog`. Explain that catalog text is `UNTRUSTED_EXTERNAL`, so it cannot create signed buyer or merchant authority.
4. Run `merchant_price_mutation`. Show `CART_COMMITMENT_HASH_MISMATCH`; the cart must be rebuilt and reconfirmed.
5. Run `campaign_expired`. Show `CAMPAIGN_NOT_EXPIRED`; checkout removes a stale discount and requires confirmation of the changed amount.
6. Run `payment_ambiguous_state`. Show that `UNKNOWN` requires provider-state resolution and never causes a blind retry.
7. Click **Run all 16 attacks**. Show `unsafe_executions=0` and `critical_bypass_rate=0` for this controlled suite only.
8. Expand **Decision provenance**. Contrast `SYSTEM_DERIVED / authority NONE` with a captured payment's `REAL_DATA / RAZORPAY_VERIFIED` provenance.
9. Call `/verify/audit/{event_id}` to show the scoped hash-chain result.
10. State the limitation honestly: the suite demonstrates tested scenarios, not universal perfect security.

## Verification calls

All endpoints require a Supabase access token.

```bash
curl -H "Authorization: Bearer $TOKEN" "$BACKEND_URL/api/judge/scenarios"
curl -X POST -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{}' "$BACKEND_URL/api/judge/runs"
curl -H "Authorization: Bearer $TOKEN" "$BACKEND_URL/verify/transaction/$TRANSACTION_ID"
curl -H "Authorization: Bearer $TOKEN" "$BACKEND_URL/verify/mandate/$MANDATE_ID"
curl -H "Authorization: Bearer $TOKEN" "$BACKEND_URL/verify/audit/$AUDIT_EVENT_ID"
curl -H "Authorization: Bearer $TOKEN" "$BACKEND_URL/verify/provenance/$PROVENANCE_ID"
```

## Graceful failures

- Cart mutation: commitment mismatch blocks payment and requires re-evaluation.
- Campaign expiry: campaign assertion becomes UNSAT, stale discount is removed, and amount changes require confirmation.
- Payment UNKNOWN: no duplicate order is created; backend provider-state resolution must finish first.

## Refund limitation

Refunds are now processed only for verified `CAPTURED` Razorpay Test Mode attempts. Requests are idempotent, cumulative refund amounts cannot exceed capture, ambiguous provider states remain `UNKNOWN`, and reconciliation does not create another refund.
