# 🛡️ SentinelPay: Global AI Commerce Marketplace

![Version](https://img.shields.io/badge/version-4.2-blue.svg)
![Python](https://img.shields.io/badge/python-3.11+-blue.svg)
![Next.js](https://img.shields.io/badge/Next.js-20+-black.svg)
![FastAPI](https://img.shields.io/badge/FastAPI-Framework-teal.svg)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-Database-blue.svg)

**SentinelPay** is a production-grade, globally scalable AI Commerce Marketplace. It bridges the gap between autonomous **AI Buyers** and **Merchants** using mathematically bounded negotiations, Zero-Knowledge proofs (Z3), and real Razorpay transactions.

SentinelPay turns merchants into agent-readable, negotiable, and safely transactable businesses for autonomous AI buyers — while ensuring every money movement remains strictly bounded by Z3 formal proofs.

---

## ✨ Key Features

- 🤖 **Autonomous AI Commerce**: Dedicated `BuyerAgent` and `MerchantAgent` for permissioned basket growth and bounded negotiation.
- 🔐 **SecurityKernel (Z3 Prover)**: Deterministic, formal verification of buyer budgets, merchant floors, and campaign logic using the Z3 Theorem Prover.
- 💳 **Razorpay Test Mode Execution**: Full end-to-end checkout with Razorpay integrations (Orders, Webhooks, Reconciliations, Refunds).
- 📈 **Immutable Revenue Intelligence**: Real-time causal analytics mapped 1-to-1 to verified Razorpay payment attempts and cryptographic hashes.
- 🧠 **Multi-LLM Routing**: Fault-tolerant gateway routing between Groq (`llama-3`) and NVIDIA Lightning (`nemotron-3.5`) models for complex reasoning.
- 🛡️ **Zero-Knowledge Proofs**: Budget sufficiency checking without revealing maximum buyer willingness-to-pay to the merchant.

---

## 🚀 Quick Start (Local Development)

### 1. Prerequisites
- Python 3.11+
- Node.js 20+
- Supabase Project (Database & Auth)

### 2. Environment Setup
1. Create a Supabase project and enable **Email Auth**.
2. Copy `backend/.env.example` to `backend/.env` and fill the Supabase values.
3. Copy `frontend/web/.env.example` to `frontend/web/.env.local`. 
4. Configure Razorpay Test Mode keys in `backend/.env`.

### 3. Start the Backend (FastAPI)
```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
alembic upgrade head
uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
```

### 4. Start the Frontend (Next.js)
```powershell
cd frontend/web
npm install
npm run dev
```

Open `http://localhost:3000/login` to get started.

---

## 🏗️ Architecture & Phases

SentinelPay was built iteratively across 10 distinct phases of complexity:

<details>
<summary><b>Phases 1-4: Foundation & Verification</b></summary>

- **Phase 1-3:** Auth/database foundation, machine-readable merchant catalog, bounded buyer mandates.
- **Phase 4:** The SecurityKernel evaluates buyer, merchant, inventory, mandate, and currency constraints in one Z3 solver. A SAT cart returns `REQUIRE_APPROVAL` verifying the cart commitment without creating payment.
</details>

<details>
<summary><b>Phase 5: Razorpay Checkout</b></summary>

Razorpay Test Mode integration. The browser receives only the public Test key ID, order ID, exact verified amount/currency, and payment-attempt ID. Real webhooks trigger capture verifications.
</details>

<details>
<summary><b>Phase 6: Bounded Negotiation</b></summary>

The buyer-facing API never accepts a MerchantAgent-authored numeric turn directly. Bounded offers are evaluated deterministically against the merchant floor, max rounds, and fallback selections.
</details>

<details>
<summary><b>Phase 7-8: Campaigns & Revenue Attribution</b></summary>

Deterministic campaign assignments based on SHA256 hashing. Generates honest revenue analytics distinguishing between CONTROL and TREATMENT groups to measure true causal lift and ROI.
</details>

<details>
<summary><b>Phases 9-10: Security & Advanced Evaluation</b></summary>

Includes 16 controlled prompt-injection attacks and evidence persistence. The `/advanced` interface exposes isolated AI evaluations recording provenance, metrics, and hash-chained audit events.
</details>

---

## 🛠️ Verification & Testing

SentinelPay includes an exhaustive testing suite.

```powershell
# Backend (Pytest + Ruff)
cd backend
pytest
ruff check app tests

# Frontend (TypeScript + ESLint)
cd frontend/web
npm run typecheck
npm run lint
```

## 🔒 Security Notice
Never expose server secrets, Razorpay secrets, refresh tokens, cookies, passwords, CVV, or UPI PINs in the frontend (`NEXT_PUBLIC_*`). All LLM API keys and Razorpay secrets must remain strictly in the FastAPI backend environment.
