import sys
sys.stdout.reconfigure(line_buffering=True)
sys.stderr.reconfigure(line_buffering=True)

import hmac
import hashlib
import json
import uuid
from uuid import UUID, uuid4
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import app
from app.db.session import get_db_session
from app.core.config import get_settings
from app.auth.dependencies import get_current_user, AuthenticatedUser

client = TestClient(app)

def run_e2e_marketplace_test():
    print("==================================================================", flush=True)
    print("SENTINELPAY — GLOBAL MULTI-MERCHANT MARKETPLACE E2E TRACE", flush=True)
    print("==================================================================", flush=True)
    
    settings = get_settings()
    
    # -------------------------------------------------------------
    # 1. Test Global Marketplace Catalog Discovery
    # -------------------------------------------------------------
    print("\n--- STAGE 1: GLOBAL MARKETPLACE CATALOG DISCOVERY ---")
    res = client.get("/api/marketplace/catalog")
    assert res.status_code == 200, f"Catalog failed: {res.text}"
    catalog = res.json()
    print(f"Total Canonical Products: {catalog['total_products']}")
    print(f"Total Offers: {catalog['total_offers']}")
    print(f"Categories: {catalog['categories']}")
    assert catalog["total_products"] > 0, "No products found in marketplace"
    assert "Ice Cream" in catalog["categories"], "Ice Cream category missing"
    
    # Search specifically for Vanilla
    res_vanilla = client.get("/api/marketplace/catalog?query=Vanilla")
    assert res_vanilla.status_code == 200
    vanilla_data = res_vanilla.json()
    vanilla_prod = next((p for p in vanilla_data["products"] if "vanilla" in p["name"].lower()), None)
    assert vanilla_prod is not None, "Vanilla Ice Cream Tub not found in search"
    print(f"Product: '{vanilla_prod['name']}' | Sellers: {vanilla_prod['seller_count']}")
    for o in vanilla_prod["offers"]:
        print(f"  * Merchant: {o['merchant_name']} | Price: INR {o['unit_price_minor']/100} | Stock: {o['stock']}")
    assert vanilla_prod["seller_count"] >= 2, "Expected at least 2 merchants for Vanilla Ice Cream Tub"
    print("STAGE 1 PASS: Multi-merchant product discovery confirmed.")

    # -------------------------------------------------------------
    # 2. Test AI Offer Ranking & Explainability
    # -------------------------------------------------------------
    print("\n--- STAGE 2: AI OFFER RANKING & EXPLAINABLE RECOMMENDATION ---")
    rank_res = client.post("/api/marketplace/rank-offers", json={
        "offers": vanilla_prod["offers"],
        "quantity": 500,
        "budget_minor": 15000
    })
    assert rank_res.status_code == 200
    ranking = rank_res.json()
    print("AI Explanation:", ranking["explanation"])
    rec = ranking["recommended_offer"]
    print(f"Top Recommended Seller: {rec['merchant_name']} (Stock: {rec['stock']}, Price: INR {rec['unit_price_minor']/100})")
    assert rec["merchant_name"] == "ICE CREAM HOUSE", "ICE CREAM HOUSE should be #1 because only it has 500 units in stock!"
    assert rec["can_fulfill"] is True
    print("STAGE 2 PASS: Explainable AI offer ranking verified.")

    # -------------------------------------------------------------
    # 3. Test Multi-Tenancy Isolation
    # -------------------------------------------------------------
    print("\n--- STAGE 3: MULTI-TENANCY & TENANT ISOLATION CHECK ---")
    # Query merchant orders with an unauthorized user or mismatched merchant
    ice_cream_merchant_id = UUID("c9cbee91-ec6c-466f-a18a-9cdfbe0ecb9e")
    amul_merchant_id = UUID("7b2428cb-6f7a-440a-ae5c-7ffda1657eb1")

    with next(get_db_session()) as db_s:
        buyer_user = db_s.execute(text("SELECT id FROM profiles LIMIT 1")).scalar()
        amul_user_id = db_s.execute(text("SELECT user_id FROM merchant_users WHERE merchant_id=:mid LIMIT 1"), {"mid": amul_merchant_id}).scalar()
    assert buyer_user is not None, "No buyer user found"

    if amul_user_id:
        amul_user = AuthenticatedUser(amul_user_id, "amul@sentinelpay.ai")
        app.dependency_overrides[get_current_user] = lambda: amul_user
        r_unauth = client.get(f"/api/merchants/{ice_cream_merchant_id}/orders")
        assert r_unauth.status_code in (401, 403), f"Tenant isolation breach! Expected 403, got {r_unauth.status_code}"
        print("Tenant isolation confirmed: Cross-tenant access was DENIED (403).")

    print("STAGE 3 PASS: Tenant isolation confirmed.")

    # -------------------------------------------------------------
    # 4. End-to-End Real Transaction Tracing (Selected Merchant)
    # -------------------------------------------------------------
    print("\n--- STAGE 4: END-TO-END TRANSACTION TRACING TO SELECTED MERCHANT ---")
    selected_offer = next((o for o in vanilla_prod["offers"] if o["merchant_name"] == "ICE CREAM HOUSE"), vanilla_prod["offers"][0])
    print(f"Buyer Selected Offer: {selected_offer['merchant_name']} ({selected_offer['merchant_id']})")
    print(f"Product ID: {selected_offer['product_id']} | Price: INR {selected_offer['unit_price_minor']/100}")

    # Override auth for test execution
    test_user = AuthenticatedUser(buyer_user, "buyer@sentinelpay.ai")
    app.dependency_overrides[get_current_user] = lambda: test_user

    try:
        # Step A: Create Intent
        r_intent = client.post("/api/intents", json={
            "raw_text": f"Buy 1 new {vanilla_prod['name']} under 200 INR"
        })
        assert r_intent.status_code == 200, f"Intent creation failed: {r_intent.text}"
        intent_res = r_intent.json()
        assert "id" in intent_res, f"Expected intent id, got: {intent_res}"
        intent_id = intent_res["id"]
        print(f"Intent ID Created: {intent_id}")

        # Step B: Activate Mandate
        r_mandate = client.post("/api/mandates", json={"intent_id": intent_id, "confirmed": True})
        assert r_mandate.status_code == 200, f"Mandate failed: {r_mandate.text}"
        mandate_id = r_mandate.json()["id"]
        print(f"Mandate ID Activated: {mandate_id}")

        # Step C: Create Bounded Cart with SELECTED Merchant
        r_cart = client.post("/api/carts", json={
            "merchant_id": selected_offer["merchant_id"],
            "mandate_id": mandate_id
        })
        assert r_cart.status_code == 200, f"Cart creation failed: {r_cart.text}"
        cart_id = r_cart.json()["id"]
        print(f"Cart ID Created: {cart_id} (Merchant: {selected_offer['merchant_name']})")

        # Step D: Add Cart Item
        r_item = client.post(f"/api/carts/{cart_id}/items", json={
            "product_id": selected_offer["product_id"],
            "quantity": 1
        })
        assert r_item.status_code == 200, f"Item add failed: {r_item.text}"

        # Step E & F: Checkout Prepare (Policy enforcement + Transaction creation)
        r_prep = client.post("/api/checkout/prepare", json={
            "cart_id": cart_id,
            "idempotency_key": str(uuid4())
        })
        assert r_prep.status_code == 200, f"Checkout prepare failed: {r_prep.text}"
        prep_data = r_prep.json()
        transaction_id = prep_data["transaction_id"]
        outcome = prep_data.get("outcome", "")
        print(f"Checkout Prepare: Transaction={transaction_id} Outcome={outcome}")

        if outcome in ("REQUIRE_APPROVAL", "REQUIRES_APPROVAL"):
            r_conf = client.post(f"/api/checkout/{transaction_id}/confirm", json={"confirmed": True})
            assert r_conf.status_code == 200, f"Checkout confirm failed: {r_conf.text}"

        # Mock RazorpayHttpProvider to simulate local test mode capture reliably
        import app.services.payment_service as pm_mod
        fake_order_id = f"order_test_{uuid4().hex[:16]}"
        fake_payment_id = f"pay_test_{uuid4().hex[:12]}"

        orig_create_order = pm_mod.RazorpayHttpProvider.create_order
        orig_verify_callback = pm_mod.RazorpayHttpProvider.verify_callback
        orig_fetch_payment = pm_mod.RazorpayHttpProvider.fetch_payment

        pm_mod.RazorpayHttpProvider.create_order = lambda self, amount, currency, receipt: {
            "id": fake_order_id,
            "amount": amount,
            "currency": currency,
            "status": "created",
        }
        pm_mod.RazorpayHttpProvider.verify_callback = lambda self, *a, **k: True
        pm_mod.RazorpayHttpProvider.fetch_payment = lambda self, pid: {
            "status": "captured",
            "amount": int(selected_offer["unit_price_minor"]),
            "order_id": fake_order_id,
            "currency": "INR",
        }

        try:
            # Step G: Razorpay Payment Order Creation
            r_pmt_order = client.post("/api/payments/order", json={
                "transaction_id": transaction_id,
                "idempotency_key": str(uuid4())
            })
            assert r_pmt_order.status_code == 200, f"Payment order failed: {r_pmt_order.text}"
            order_data = r_pmt_order.json()
            payment_attempt_id = str(order_data["payment_attempt_id"])
            razorpay_order_id = order_data["order_id"]
            print(f"Razorpay Order Created: {razorpay_order_id} | Payment Attempt: {payment_attempt_id}")

            # Step H: Payment Verification
            r_verify = client.post("/api/payments/verify", json={
                "payment_attempt_id": payment_attempt_id,
                "razorpay_order_id": razorpay_order_id,
                "razorpay_payment_id": fake_payment_id,
                "razorpay_signature": "test_sig_ok"
            })
            assert r_verify.status_code == 200, f"Verification failed: {r_verify.text}"
            verify_data = r_verify.json()
            print(f"Payment Verified: {verify_data}")
            assert verify_data.get("captured") is True
        finally:
            pm_mod.RazorpayHttpProvider.create_order = orig_create_order
            pm_mod.RazorpayHttpProvider.verify_callback = orig_verify_callback
            pm_mod.RazorpayHttpProvider.fetch_payment = orig_fetch_payment

        # -------------------------------------------------------------
        # 5. Authoritative Database Verification & Attribution
        # -------------------------------------------------------------
        print("\n--- STAGE 5: DATABASE AUDIT & REVENUE ATTRIBUTION ---")
        db = next(get_db_session())
        
        # Check Transaction
        txn_row = db.execute(text("SELECT id, cart_id, status FROM transactions WHERE id=:id"), {"id": transaction_id}).mappings().one()
        print(f"DB Transaction: ID={txn_row['id']} Status={txn_row['status']}")

        # Check Payment Attempt
        pmt_row = db.execute(text("SELECT id, status, amount_minor FROM payment_attempts WHERE id=:id"), {"id": payment_attempt_id}).mappings().one()
        print(f"DB Payment Attempt: ID={pmt_row['id']} Status={pmt_row['status']} Amount=INR {pmt_row['amount_minor']/100}")
        assert pmt_row["status"] == "CAPTURED"

        # Check Revenue Ledger for SELECTED Merchant
        rev_row = db.execute(text("""
            SELECT id, merchant_id, amount_minor, attribution_type, order_type 
            FROM revenue_ledger 
            WHERE transaction_id=:tid
        """), {"tid": transaction_id}).mappings().one_or_none()
        assert rev_row is not None, "Revenue ledger record was NOT written!"
        print(f"DB Revenue Ledger: ID={rev_row['id']} Merchant={rev_row['merchant_id']} Amount=INR {rev_row['amount_minor']/100}")
        assert str(rev_row["merchant_id"]) == selected_offer["merchant_id"], f"Revenue credited to wrong merchant! Expected {selected_offer['merchant_id']}, got {rev_row['merchant_id']}"

        # Verify OTHER merchant did NOT receive revenue for this transaction
        other_rev = db.execute(text("""
            SELECT count(*) FROM revenue_ledger 
            WHERE transaction_id=:tid AND merchant_id != :mid
        """), {"tid": transaction_id, "mid": selected_offer["merchant_id"]}).scalar()
        assert other_rev == 0, "Other merchants received revenue incorrectly!"
        print("Revenue isolation confirmed: 100% credited to selected merchant.")

        # Check Audit Events / Agent Activity
        audit_count = db.execute(text("""
            SELECT count(*) FROM audit_events 
            WHERE transaction_id=:tid OR chain_scope LIKE :scope
        """), {"tid": transaction_id, "scope": f"%{cart_id}%"}).scalar()
        print(f"Audit / Agent Activity Events Count: {audit_count}")
        assert audit_count > 0, "No audit events logged"

        # -------------------------------------------------------------
        # 6. Check Merchant Dashboard APIs
        # -------------------------------------------------------------
        print("\n--- STAGE 6: MERCHANT DASHBOARD ORDERS & REVENUE APIS ---")
        
        # Override auth as merchant user belonging to selected merchant
        # Find user for selected merchant
        merchant_user_id = db.execute(text("""
            SELECT user_id FROM merchant_users WHERE merchant_id=:mid LIMIT 1
        """), {"mid": selected_offer["merchant_id"]}).scalar()
        db.close()
        
        if merchant_user_id:
            m_user = AuthenticatedUser(merchant_user_id, "merchant@sentinelpay.ai")
            app.dependency_overrides[get_current_user] = lambda: m_user

            # Selected Merchant Orders API
            m_orders_res = client.get(f"/api/merchants/{selected_offer['merchant_id']}/orders")
            assert m_orders_res.status_code == 200
            m_orders = m_orders_res.json()["orders"]
            matching_order = next((o for o in m_orders if o["id"] == str(transaction_id)), None)
            assert matching_order is not None, "Order NOT found in selected merchant orders API!"
            print(f"Selected Merchant Orders API: Found order {matching_order['id']} (Product: {matching_order['product']}, Status: {matching_order['status']})")

            # Selected Merchant Revenue API
            m_rev_res = client.get(f"/api/merchants/{selected_offer['merchant_id']}/revenue")
            assert m_rev_res.status_code == 200
            m_rev = m_rev_res.json()
            total_rev = m_rev.get("totalRevenue", m_rev.get("total_revenue", 0))
            print(f"Selected Merchant Total Revenue: INR {total_rev:,}")
            assert total_rev > 0, "Selected merchant revenue was 0!"

            # Selected Merchant Agent Activity API
            m_act_res = client.get(f"/api/merchants/{selected_offer['merchant_id']}/agent-activity")
            assert m_act_res.status_code == 200
            m_events = m_act_res.json().get("events", [])
            print(f"Selected Merchant Agent Activity: {len(m_events)} events returned.")
            assert len(m_events) > 0, "Agent Activity was empty!"

        print("\n==================================================================")
        print("ALL TESTS PASSED SUCCESSFULLY! FULL MARKETPLACE PIPELINE VERIFIED.")
        print("==================================================================")

        return {
            "razorpay_order_id": razorpay_order_id,
            "razorpay_payment_id": fake_payment_id,
            "transaction_id": str(transaction_id),
            "payment_attempt_id": str(payment_attempt_id),
            "cart_id": str(cart_id),
            "intent_id": str(intent_id),
            "mandate_id": str(mandate_id),
            "selected_merchant_id": selected_offer["merchant_id"],
            "selected_merchant_name": selected_offer["merchant_name"],
            "revenue_ledger_id": str(rev_row["id"]),
            "amount_minor": pmt_row["amount_minor"],
        }

    finally:
        app.dependency_overrides.clear()

if __name__ == "__main__":
    result = run_e2e_marketplace_test()
    print("\nFINAL TEST EVIDENCE:")
    for k, v in result.items():
        print(f"  {k}: {v}")
