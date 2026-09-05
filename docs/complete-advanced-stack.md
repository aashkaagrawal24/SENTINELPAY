# SentinelPay Complete Advanced Stack

## Provider Boundary

The configured model route is Groq, then NVIDIA NIM, then fail closed. OpenRouter is intentionally excluded by product-owner revision. Models remain proposal-only and cannot authorize payment.

The Razorpay webhook endpoint is implemented and fails closed without `RAZORPAY_WEBHOOK_SECRET`. The deployment secret is intentionally configured only after a public HTTPS webhook URL exists.

## External Intelligence

The platform registry contains OLX, Quikr, Facebook Marketplace, IndiaMART, TradeIndia, Local Classifieds, Meesho, ShopClues, Snapdeal, JioMart, Amazon, Flipkart, Myntra, Nykaa, Tata CLiQ, Croma, and Reliance Digital.

All adapters are capability-aware. Controlled snapshots can be queried in parallel with timeout, rate-limit, normalization, product identity, partial-failure, provenance, and result-merge handling. No external platform is represented as autonomous checkout-capable. Unsupported purchase actions return `HANDOFF`.

## Strategy and Pricing

- Negotiability uses scikit-learn Logistic Regression with a reproducible 240-row controlled dataset, exported artifact, precision, recall, F1, ROC-AUC and Brier calibration score.
- Risk-adjusted acquisition cost stores every amount with source and trust class.
- LinUCB uses per-action `A` matrices, `b` vectors, confidence bounds, reward updates and PostgreSQL persistence.
- CFR uses hidden buyer values, hidden seller floors, three bargaining rounds, information sets, regret accumulation and average-strategy updates.

## Analytics and Privacy

- DoWhy identifies a backdoor estimand from campaign observations, estimates treatment effect and runs random-common-cause and placebo refutations.
- Diffprivlib adds bounded noise only to aggregate analytics with explicit epsilon. Payments, transactions, policies and audit truth are never noised.
- NetworkX builds and queries a DAG analytical view while PostgreSQL remains authoritative.
- Paillier 2048-bit homomorphic encryption performs encrypted aggregate sums. Encrypted comparison is explicitly unsupported.
- A Circom 2 circuit and Groth16/snarkjs prover verify private budget sufficiency. The private witness is written only inside an automatically deleted temporary directory. The checked-in setup is a controlled Test Mode ceremony, not a production multi-party ceremony or third-party audit. The earlier Pedersen/Schnorr proof remains a compatibility implementation only.
- BLS12-381 Proof-of-Possession aggregates distinct Mandate, Policy and Risk verifier signatures.
- The Wesolowski repeated-squaring VDF protects sealed-bid reveal timing; it is not added to retail checkout latency.

## B2B Procurement

The controlled procurement path is RFQ constraints, sealed-bid commitment, VDF delay, reveal verification, reverse-auction VCG winner determination, Z3-constrained quantity allocation, delivery/risk objective, winner payments and controlled settlement journal. It never fabricates multi-merchant Razorpay capture.

## Unified Payment Gate

High-value transactions or callers requesting advanced verification add ZK, MandateVerifier, PolicyVerifier, RiskVerifier, BLS and provenance results as tracked boolean assertions in the same unified Z3 solver call. Missing evidence is UNSAT. Cart commitment, replay, human confirmation, PaymentService and trusted provider verification remain mandatory.

## Reproducible Commands

```powershell
cd backend
.\.venv\Scripts\python.exe scripts\train_negotiability.py
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check app tests migrations scripts

cd ..\frontend\web
npm run typecheck
npm run lint
npm run build
```
