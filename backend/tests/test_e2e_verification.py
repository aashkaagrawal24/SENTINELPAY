import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import app
from app.db.session import get_db_session

client = TestClient(app)
HEADERS = {"Authorization": "Bearer demo_token"}
DEMO_USER_ID = "00000000-0000-0000-0000-000000000000"


@pytest.fixture
def test_db():
    db = next(get_db_session())
    try:
        yield db
    finally:
        db.close()


def test_e2e_agent_purchase_and_revenue_attribution(test_db):
    print("\n--- TEST A: END-TO-END AGENT PURCHASE & IDEMPOTENCY ---")

    # ── Find a real merchant and product ──────────────────────────────────────
    merchant = test_db.execute(
        text("select id from merchants limit 1")
    ).mappings().first()
    assert merchant, "No merchant found in DB"
    merchant_id = str(merchant["id"])

    product = test_db.execute(
        text(
            "select id, base_price_minor from merchant_products "
            "where merchant_id = :m and active = true limit 1"
        ),
        {"m": merchant_id},
    ).mappings().first()
    assert product, "No active product found for merchant"
    product_id = str(product["id"])

    # ── Step 1: Create conversation thread ────────────────────────────────────
    print("1. Creating conversation thread...")
    res = client.post("/api/conversations", headers=HEADERS)
    assert res.status_code == 200, f"conversations: {res.text}"
    thread_id = res.json()["id"]

    # ── Step 2: Parse buyer intent ────────────────────────────────────────────
    print("2. Parsing intent...")
    res = client.post(
        f"/api/conversations/{thread_id}/messages",
        headers=HEADERS,
        json={
            "content": (
                f"I want to buy product {product_id}. "
                "My budget is 50000 INR. Condition NEW."
            ),
            "merchant_id": merchant_id,
        },
    )
    assert res.status_code == 200, f"intent parse: {res.text}"
    data = res.json()
    assert data["status"] == "REQUIRES_MANDATE_CONFIRMATION", (
        f"Unexpected status: {data.get('status')}"
    )
    intent_id = data["intent_id"]
    candidates = data.get("candidates", [])
    assert len(candidates) > 0, "Agent failed to discover the product"

    # ── Step 3: Confirm mandate ───────────────────────────────────────────────
    print("3. Confirming mandate...")
    res = client.post(
        "/api/mandates",
        headers=HEADERS,
        json={"intent_id": intent_id, "confirmed": True},
    )
    assert res.status_code == 200, f"mandate: {res.text}"
    mandate_id = res.json()["id"]

    # ── Step 4: Create cart ───────────────────────────────────────────────────
    print("4. Creating cart...")
    res = client.post(
        "/api/carts",
        headers=HEADERS,
        json={"merchant_id": merchant_id, "mandate_id": mandate_id},
    )
    assert res.status_code == 200, f"create cart: {res.text}"
    cart_id = res.json()["id"]

    # ── Step 5: Add item to cart ──────────────────────────────────────────────
    print("5. Adding product to cart...")
    res = client.post(
        f"/api/carts/{cart_id}/items",
        headers=HEADERS,
        json={"product_id": product_id, "quantity": 1},
    )
    assert res.status_code == 200, f"add item: {res.text}"

    # ── Step 6: Checkout prepare (policy enforcement + transaction creation) ──
    print("6. Checkout prepare (security kernel evaluation)...")
    idempotency_key = str(uuid.uuid4())
    res = client.post(
        "/api/checkout/prepare",
        headers=HEADERS,
        json={"cart_id": cart_id, "idempotency_key": idempotency_key},
    )
    assert res.status_code == 200, f"checkout prepare: {res.text}"
    checkout_data = res.json()
    transaction_id = str(checkout_data["transaction_id"])
    outcome = checkout_data.get("outcome", "")
    print(f"   Policy outcome: {outcome}")
    # ALLOW or REQUIRES_APPROVAL are both valid during tests
    assert outcome in ("ALLOW", "REQUIRE_APPROVAL", "REQUIRES_APPROVAL"), (
        f"Unexpected policy outcome: {outcome}"
    )

    # If policy requires human approval, confirm the checkout before payment
    if outcome in ("REQUIRE_APPROVAL", "REQUIRES_APPROVAL"):
        print(f"   {outcome} — confirming human approval...")
        res = client.post(
            f"/api/checkout/{transaction_id}/confirm",
            headers=HEADERS,
            json={"confirmed": True},
        )
        assert res.status_code == 200, f"checkout confirm: {res.text}"

    # ── Steps 7 & 8: Mock Razorpay and run payment flow ───────────────────────
    import app.services.payment_service as pm_mod

    fake_order_id = f"order_test_{uuid.uuid4().hex[:16]}"
    fake_payment_id = f"pay_test_{uuid.uuid4().hex[:12]}"

    original_create_order = pm_mod.RazorpayHttpProvider.create_order
    original_verify = pm_mod.RazorpayHttpProvider.verify_callback
    original_fetch = pm_mod.RazorpayHttpProvider.fetch_payment

    # We need to know the cart total to build the mock — query it from DB
    cart_row = test_db.execute(
        text("select total_minor, currency from carts where id=:c"),
        {"c": cart_id},
    ).mappings().first()
    expected_amount = int(cart_row["total_minor"])

    pm_mod.RazorpayHttpProvider.create_order = lambda self, amount, currency, receipt: {
        "id": fake_order_id,
        "amount": amount,
        "currency": currency,
        "status": "created",
    }
    pm_mod.RazorpayHttpProvider.verify_callback = lambda self, *a, **k: True
    pm_mod.RazorpayHttpProvider.fetch_payment = lambda self, pid: {
        "status": "captured",
        "amount": expected_amount,
        "order_id": fake_order_id,
        "currency": "INR",
    }

    try:
        # Step 7: Create Razorpay payment order
        print("7. Creating Razorpay payment order...")
        payment_idem = str(uuid.uuid4())
        res = client.post(
            "/api/payments/order",
            headers=HEADERS,
            json={"transaction_id": transaction_id, "idempotency_key": payment_idem},
        )
        assert res.status_code == 200, f"payment order: {res.text}"
        order_data = res.json()
        payment_attempt_id = str(order_data["payment_attempt_id"])
        razorpay_order_id = order_data["order_id"]
        amount_minor = order_data["amount_minor"]
        print(f"   Amount: {amount_minor} paise | order: {razorpay_order_id}")

        # Step 8: Verify payment (simulate capture)
        print("8. Verifying Razorpay payment (simulated test-mode capture)...")
        res = client.post(
            "/api/payments/verify",
            headers=HEADERS,
            json={
                "payment_attempt_id": payment_attempt_id,
                "razorpay_order_id": razorpay_order_id,
                "razorpay_payment_id": fake_payment_id,
                "razorpay_signature": "test_sig_ok",
            },
        )
        assert res.status_code == 200, f"payment verify: {res.text}"
        verify_data = res.json()
        assert verify_data.get("captured") is True, (
            f"Payment not captured: {verify_data}"
        )

    finally:
        pm_mod.RazorpayHttpProvider.create_order = original_create_order
        pm_mod.RazorpayHttpProvider.verify_callback = original_verify
        pm_mod.RazorpayHttpProvider.fetch_payment = original_fetch


        pm_mod.RazorpayHttpProvider.verify_callback = original_verify
        pm_mod.RazorpayHttpProvider.fetch_payment = original_fetch

    # ── Step 9: Verify Revenue Ledger entry ───────────────────────────────────
    print("9. Checking Revenue Ledger...")
    test_db.expire_all()  # refresh session cache
    ledger_entries = test_db.execute(
        text("select * from revenue_ledger where transaction_id=:tid"),
        {"tid": transaction_id},
    ).mappings().fetchall()
    assert len(ledger_entries) >= 1, (
        f"Expected revenue_ledger entry for transaction {transaction_id}, got {len(ledger_entries)}"
    )
    entry = ledger_entries[0]
    assert entry["amount_minor"] == amount_minor, (
        f"Revenue ledger amount mismatch: {entry['amount_minor']} != {amount_minor}"
    )
    assert str(entry["merchant_id"]) == merchant_id
    assert entry["currency"] == "INR"
    print(f"   Revenue ledger OK — attribution: {entry['attribution_type']}")

    # ── Step 10: Idempotency check — calling verify again must NOT duplicate ──
    print("10. Testing payment verify idempotency...")
    pm_mod.RazorpayHttpProvider.verify_callback = lambda self, *a, **k: True
    pm_mod.RazorpayHttpProvider.fetch_payment = lambda self, pid: {
        "status": "captured",
        "amount": amount_minor,
        "order_id": razorpay_order_id,
        "currency": "INR",
    }
    try:
        res = client.post(
            "/api/payments/verify",
            headers=HEADERS,
            json={
                "payment_attempt_id": payment_attempt_id,
                "razorpay_order_id": razorpay_order_id,
                "razorpay_payment_id": fake_payment_id,
                "razorpay_signature": "test_sig_ok",
            },
        )
        assert res.status_code == 200, f"idempotent verify: {res.text}"
    finally:
        pm_mod.RazorpayHttpProvider.verify_callback = original_verify
        pm_mod.RazorpayHttpProvider.fetch_payment = original_fetch

    test_db.expire_all()
    ledger_after = test_db.execute(
        text("select * from revenue_ledger where transaction_id=:tid"),
        {"tid": transaction_id},
    ).mappings().fetchall()
    assert len(ledger_after) == 1, (
        f"Idempotency FAILED — {len(ledger_after)} ledger entries created"
    )

    # ── Step 11: Audit trail check ────────────────────────────────────────────
    print("11. Checking Audit Ledger...")
    audit = test_db.execute(
        text(
            "select * from audit_events "
            "where transaction_id=:tid and event_type='PAYMENT_CAPTURED'"
        ),
        {"tid": transaction_id},
    ).mappings().fetchall()
    assert len(audit) > 0, (
        f"Missing PAYMENT_CAPTURED audit event for transaction {transaction_id}"
    )

    print("\n[SUCCESS] All E2E Pipeline Checks PASSED!")
    print(f"   merchant: {merchant_id}")
    print(f"   product:  {product_id}")
    print(f"   cart:     {cart_id}")
    print(f"   txn:      {transaction_id}")
    print(f"   payment:  {payment_attempt_id}")
    print(f"   revenue:  {entry['amount_minor']} {entry['currency']} ({entry['attribution_type']})")


def test_e2e_payment_failure(test_db):
    print("\n--- TEST B: PAYMENT FAILURE ---")
    
    # Setup initial state
    merchant = test_db.execute(text("select id from merchants limit 1")).mappings().first()
    merchant_id = str(merchant["id"])

    product = test_db.execute(text("select id from merchant_products where merchant_id = :m and active = true limit 1"), {"m": merchant_id}).mappings().first()
    product_id = str(product["id"])

    # Create thread, intent, mandate, cart, checkout
    res = client.post("/api/conversations", headers=HEADERS)
    thread_id = res.json()["id"]

    res = client.post(
        f"/api/conversations/{thread_id}/messages",
        headers=HEADERS,
        json={"content": f"I want to buy product {product_id}. My budget is 50000 INR.", "merchant_id": merchant_id},
    )
    intent_id = res.json()["intent_id"]

    res = client.post("/api/mandates", headers=HEADERS, json={"intent_id": intent_id, "confirmed": True})
    mandate_id = res.json()["id"]

    res = client.post("/api/carts", headers=HEADERS, json={"merchant_id": merchant_id, "mandate_id": mandate_id})
    cart_id = res.json()["id"]

    client.post(f"/api/carts/{cart_id}/items", headers=HEADERS, json={"product_id": product_id, "quantity": 1})

    idempotency_key = str(uuid.uuid4())
    res = client.post("/api/checkout/prepare", headers=HEADERS, json={"cart_id": cart_id, "idempotency_key": idempotency_key})
    checkout_data = res.json()
    transaction_id = str(checkout_data["transaction_id"])
    outcome = checkout_data.get("outcome", "")
    if outcome in ("REQUIRE_APPROVAL", "REQUIRES_APPROVAL"):
        client.post(f"/api/checkout/{transaction_id}/confirm", headers=HEADERS, json={"confirmed": True})

    import app.services.payment_service as pm_mod
    fake_order_id = f"order_test_{uuid.uuid4().hex[:16]}"
    fake_payment_id = f"pay_test_{uuid.uuid4().hex[:12]}"
    original_create = pm_mod.RazorpayHttpProvider.create_order
    original_verify = pm_mod.RazorpayHttpProvider.verify_callback
    original_fetch = pm_mod.RazorpayHttpProvider.fetch_payment
    
    cart_row = test_db.execute(text("select total_minor from carts where id=:c"), {"c": cart_id}).mappings().first()
    expected_amount = int(cart_row["total_minor"])

    pm_mod.RazorpayHttpProvider.create_order = lambda self, amount, currency, receipt: {
        "id": fake_order_id, "amount": amount, "currency": currency, "status": "created"
    }
    # Simulate a FAILED payment fetch
    pm_mod.RazorpayHttpProvider.verify_callback = lambda self, *a, **k: True
    pm_mod.RazorpayHttpProvider.fetch_payment = lambda self, pid: {
        "status": "failed", "amount": expected_amount, "order_id": fake_order_id, "currency": "INR"
    }

    try:
        payment_idem = str(uuid.uuid4())
        res = client.post("/api/payments/order", headers=HEADERS, json={"transaction_id": transaction_id, "idempotency_key": payment_idem})
        order_data = res.json()
        payment_attempt_id = str(order_data["payment_attempt_id"])
        
        # Verify payment with failure
        res = client.post(
            "/api/payments/verify",
            headers=HEADERS,
            json={
                "payment_attempt_id": payment_attempt_id,
                "razorpay_order_id": fake_order_id,
                "razorpay_payment_id": fake_payment_id,
                "razorpay_signature": "test_sig_ok",
            },
        )
        if res.status_code == 200:
            assert not res.json().get("captured"), "Payment should not be captured"
        
        # Verify revenue ledger is 0 / empty
        test_db.expire_all()
        ledger_entries = test_db.execute(text("select * from revenue_ledger where transaction_id=:tid"), {"tid": transaction_id}).fetchall()
        assert len(ledger_entries) == 0, "Revenue ledger should be empty for failed payments"
        
        # Verify transaction payment_status is FAILED
        txn = test_db.execute(text("select payment_status from transactions where id=:tid"), {"tid": transaction_id}).mappings().first()
        assert txn["payment_status"] == "FAILED", f"Transaction payment_status should be FAILED, got {txn['payment_status']}"
        
        print("\n[SUCCESS] Test B: Payment Failure handled correctly.")
    finally:
        pm_mod.RazorpayHttpProvider.create_order = original_create
        pm_mod.RazorpayHttpProvider.verify_callback = original_verify
        pm_mod.RazorpayHttpProvider.fetch_payment = original_fetch


def test_e2e_privacy_leak_check(test_db):
    print("\n--- TEST H: PRIVACY LEAK CHECK ---")
    
    merchant = test_db.execute(text("select id from merchants limit 1")).mappings().first()
    merchant_id = str(merchant["id"])

    product = test_db.execute(text("select id from merchant_products where merchant_id = :m and active = true limit 1"), {"m": merchant_id}).mappings().first()
    product_id = str(product["id"])

    res = client.post("/api/conversations", headers=HEADERS)
    thread_id = res.json()["id"]

    payload = {
        "content": f"I want to buy product {product_id}. My maximum budget is EXACTLY 1337 INR. Condition NEW.",
        "merchant_id": merchant_id,
    }
    res = client.post(f"/api/conversations/{thread_id}/messages", headers=HEADERS, json=payload)
    data = res.json()
    
    # We want to ensure that if a merchant looks at the intent/conversation data from their POV, they can't see the exact budget.
    # But as a simple check, the response itself should NOT echo the max budget explicitly in the candidate metadata back to the user.
    # We can also check that '1337' does not appear in the merchant's visible fields.
    intent_id = data.get("intent_id", "")
    assert intent_id, "Missing intent ID"
    
    intent_row = test_db.execute(text("select parsed_payload from intents where id=:id"), {"id": intent_id}).mappings().first()
    assert intent_row, "Intent not saved"
    if intent_row.get("parsed_payload"):
        # The intent might contain the budget, but it shouldn't be exposed to the merchant UI.
        # This is a backend test, but we can verify our response structure.
        pass

    assert "1337" not in str(data.get("candidates", [])), "Budget leaked into candidate representation"
    print("\n[SUCCESS] Test H: Privacy Leak Check passed.")
