import json
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.commerce_routes import load_cart, security_inputs
from app.schemas.payment import PaymentStatus, RefundStatus
from app.services.payment_service import (
    PaymentAttemptClaim,
    PaymentAttemptRecord,
    PaymentContext,
    PaymentStateMachine,
    RefundRecord,
)
from app.services.security_kernel import SecurityKernel


class SqlPaymentRepository:
    def __init__(self, db: Session):
        self.db = db

    @staticmethod
    def _attempt(row) -> PaymentAttemptRecord:
        return PaymentAttemptRecord(
            id=row["id"],
            transaction_id=row["transaction_id"],
            idempotency_key=row["idempotency_key"],
            amount_minor=row["amount_minor"],
            currency=row["currency"],
            status=PaymentStatus(row["status"]),
            razorpay_order_id=row.get("razorpay_order_id"),
            razorpay_payment_id=row.get("razorpay_payment_id"),
        )

    def lock_context(self, transaction_id: UUID) -> PaymentContext:
        transaction = (
            self.db.execute(
                text("select * from transactions where id=:id for update"), {"id": transaction_id}
            )
            .mappings()
            .one()
        )
        cart = load_cart(self.db, transaction["cart_id"], transaction["user_id"])
        mandate, _policy, policy_context = security_inputs(self.db, cart, dict(transaction))
        commitment = self.db.execute(
            text("select approved_hash from cart_commitments where transaction_id=:id"),
            {"id": transaction_id},
        ).scalar_one()
        decision = SecurityKernel().policy_service.evaluate(policy_context)
        return PaymentContext(
            transaction_id=transaction["id"],
            transaction_status=transaction["status"],
            human_confirmed=transaction["human_confirmed"] or policy_context.auto_purchase_allowed,
            mandate_id=mandate["id"],
            mandate_status=mandate["status"],
            execution_count=mandate["execution_count"],
            max_executions=mandate["max_executions"],
            cart=cart,
            approved_hash=commitment,
            security_fresh=decision.solver_result == "SAT",
        )

    def reusable_attempt(
        self, transaction_id: UUID, idempotency_key: str
    ) -> PaymentAttemptRecord | None:
        row = (
            self.db.execute(
                text(
                    "select * from payment_attempts where transaction_id=:transaction and (idempotency_key=:key or status in ('CREATED','ORDER_CREATED','PAYMENT_PENDING','CAPTURED','UNKNOWN')) order by created_at desc limit 1"
                ),
                {"transaction": transaction_id, "key": idempotency_key},
            )
            .mappings()
            .one_or_none()
        )
        return self._attempt(row) if row else None

    def create_attempt(self, context: PaymentContext, idempotency_key: str) -> PaymentAttemptClaim:
        row = (
            self.db.execute(
                text(
                    "insert into payment_attempts(transaction_id,idempotency_key,amount_minor,currency,status) values(:transaction,:key,:amount,:currency,'CREATED') on conflict (transaction_id) where status in ('CREATED','ORDER_CREATED','PAYMENT_PENDING','CAPTURED','UNKNOWN') do nothing returning *"
                ),
                {
                    "transaction": context.transaction_id,
                    "key": idempotency_key,
                    "amount": context.cart["total_minor"],
                    "currency": context.cart["currency"],
                },
            )
            .mappings()
            .one_or_none()
        )
        created = row is not None
        if not row:
            row = (
                self.db.execute(
                    text(
                        "select * from payment_attempts where transaction_id=:transaction and status in ('CREATED','ORDER_CREATED','PAYMENT_PENDING','CAPTURED','UNKNOWN') order by created_at desc limit 1"
                    ),
                    {"transaction": context.transaction_id},
                )
                .mappings()
                .one()
            )
        if created:
            self.db.execute(
                text(
                    "update transactions set active_payment_attempt_id=:attempt,payment_status='CREATED' where id=:transaction"
                ),
                {"attempt": row["id"], "transaction": context.transaction_id},
            )
            transaction = self.db.execute(
                text("select campaign_offer_id from transactions where id=:id"),
                {"id": context.transaction_id},
            ).mappings().one()
            if transaction["campaign_offer_id"]:
                reservation = self.db.execute(
                    text(
                        """update campaigns c set reserved_discount_budget_minor=c.reserved_discount_budget_minor+o.discount_minor,
                        reserved_redemptions=c.reserved_redemptions+1 from campaign_offers o
                        where o.id=:offer and o.campaign_id=c.id and o.status='APPLIED' and c.status='ACTIVE'
                        and c.start_time<=now() and c.end_time>now()
                        and c.used_discount_budget_minor+c.reserved_discount_budget_minor+o.discount_minor<=c.total_discount_budget_minor
                        and c.current_redemptions+c.reserved_redemptions<c.maximum_redemptions
                        returning c.id,o.discount_minor"""
                    ),
                    {"offer": transaction["campaign_offer_id"]},
                ).mappings().one_or_none()
                if not reservation:
                    self.db.rollback()
                    raise RuntimeError("Campaign reservation failed closed")
                self.db.execute(
                    text(
                        """insert into campaign_redemptions(campaign_id,offer_id,transaction_id,discount_minor,status)
                        values(:campaign,:offer,:transaction,:discount,'RESERVED')
                        on conflict(offer_id) do update set transaction_id=excluded.transaction_id,
                        discount_minor=excluded.discount_minor,status='RESERVED',released_at=null"""
                    ),
                    {
                        "campaign": reservation["id"],
                        "offer": transaction["campaign_offer_id"],
                        "transaction": context.transaction_id,
                        "discount": reservation["discount_minor"],
                    },
                )
        self.db.commit()
        return PaymentAttemptClaim(self._attempt(row), created)

    def set_order(
        self, attempt_id: UUID, order_id: str, safe_payload: dict
    ) -> PaymentAttemptRecord:
        row = (
            self.db.execute(
                text("select * from payment_attempts where id=:id for update"), {"id": attempt_id}
            )
            .mappings()
            .one()
        )
        PaymentStateMachine.ensure(PaymentStatus(row["status"]), PaymentStatus.ORDER_CREATED)
        updated = (
            self.db.execute(
                text(
                    "update payment_attempts set razorpay_order_id=:order,status='ORDER_CREATED',provider_payload_safe=cast(:payload as jsonb) where id=:id returning *"
                ),
                {"order": order_id, "payload": json.dumps(safe_payload), "id": attempt_id},
            )
            .mappings()
            .one()
        )
        self.db.execute(
            text("update transactions set payment_status='ORDER_CREATED' where id=:id"),
            {"id": row["transaction_id"]},
        )
        self.db.commit()
        return self._attempt(updated)

    def transition(
        self,
        attempt_id: UUID,
        target: PaymentStatus,
        payment_id: str | None = None,
        safe_payload: dict | None = None,
    ) -> PaymentAttemptRecord:
        row = (
            self.db.execute(
                text("select * from payment_attempts where id=:id for update"), {"id": attempt_id}
            )
            .mappings()
            .one()
        )
        current = PaymentStatus(row["status"])
        PaymentStateMachine.ensure(current, target)
        if current == target:
            return self._attempt(row)
        updated = (
            self.db.execute(
                text(
                    "update payment_attempts set status=:status,razorpay_payment_id=coalesce(:payment,razorpay_payment_id),provider_payload_safe=case when cast(:payload as text) is null then provider_payload_safe else cast(:payload as jsonb) end where id=:id and status=:current returning *"
                ),
                {
                    "status": target.value,
                    "payment": payment_id,
                    "payload": json.dumps(safe_payload) if safe_payload is not None else None,
                    "id": attempt_id,
                    "current": current.value,
                },
            )
            .mappings()
            .one()
        )
        self.db.execute(
            text("update transactions set payment_status=:status where id=:id"),
            {"status": target.value, "id": row["transaction_id"]},
        )
        if target == PaymentStatus.FAILED:
            released = self.db.execute(
                text(
                    """update campaign_redemptions set status='RELEASED',released_at=now()
                    where transaction_id=:transaction and status='RESERVED' returning campaign_id,discount_minor"""
                ),
                {"transaction": row["transaction_id"]},
            ).mappings().one_or_none()
            if released:
                self.db.execute(
                    text(
                        """update campaigns set reserved_discount_budget_minor=reserved_discount_budget_minor-:discount,
                        reserved_redemptions=reserved_redemptions-1 where id=:campaign"""
                    ),
                    {"discount": released["discount_minor"], "campaign": released["campaign_id"]},
                )
        self.db.commit()
        return self._attempt(updated)

    def capture_once(
        self, attempt_id: UUID, payment_id: str, safe_payload: dict
    ) -> PaymentAttemptRecord:
        row = (
            self.db.execute(
                text("select * from payment_attempts where id=:id for update"), {"id": attempt_id}
            )
            .mappings()
            .one()
        )
        if row["status"] == PaymentStatus.CAPTURED:
            return self._attempt(row)
        PaymentStateMachine.ensure(PaymentStatus(row["status"]), PaymentStatus.CAPTURED)
        transaction = (
            self.db.execute(
                text("select * from transactions where id=:id for update"),
                {"id": row["transaction_id"]},
            )
            .mappings()
            .one()
        )
        consumed = self.db.execute(
            text(
                "update mandates set execution_count=execution_count+1,status=case when execution_count+1>=max_executions then 'CONSUMED' else status end where id=:id and status='ACTIVE' and execution_count<max_executions"
            ),
            {"id": transaction["mandate_id"]},
        )
        if consumed.rowcount != 1:
            self.db.rollback()
            raise RuntimeError("Mandate capture replay blocked")
        updated = (
            self.db.execute(
                text(
                    "update payment_attempts set status='CAPTURED',razorpay_payment_id=:payment,provider_payload_safe=cast(:payload as jsonb),verified_at=now() where id=:id returning *"
                ),
                {"payment": payment_id, "payload": json.dumps(safe_payload), "id": attempt_id},
            )
            .mappings()
            .one()
        )
        self.db.execute(
            text("update transactions set status='SUCCESS',payment_status='CAPTURED' where id=:id"),
            {"id": transaction["id"]},
        )
        self.db.execute(
            text(
                "update agent_sessions set converted=true,transaction_id=:transaction,status='COMPLETED',ended_at=now() where mandate_id=:mandate"
            ),
            {"transaction": transaction["id"], "mandate": transaction["mandate_id"]},
        )
        self.db.execute(
            text(
                """update campaign_assignments set converted=true,transaction_id=:transaction
                where mandate_id=:mandate and transaction_id is null"""
            ),
            {"transaction": transaction["id"], "mandate": transaction["mandate_id"]},
        )
        self.db.execute(
            text(
                "update upsell_events set transaction_id=:transaction where cart_id=:cart and accepted and transaction_id is null"
            ),
            {"transaction": transaction["id"], "cart": transaction["cart_id"]},
        )
        self.db.execute(
            text(
                "update cross_sell_events set transaction_id=:transaction where cart_id=:cart and accepted and transaction_id is null"
            ),
            {"transaction": transaction["id"], "cart": transaction["cart_id"]},
        )
        redemption = self.db.execute(
            text(
                """update campaign_redemptions set status='REDEEMED',redeemed_at=now()
                where transaction_id=:transaction and status='RESERVED' returning campaign_id,offer_id,discount_minor"""
            ),
            {"transaction": transaction["id"]},
        ).mappings().one_or_none()
        if redemption:
            campaign_state = self.db.execute(
                text(
                    """update campaigns set reserved_discount_budget_minor=reserved_discount_budget_minor-:discount,
                    reserved_redemptions=reserved_redemptions-1,used_discount_budget_minor=used_discount_budget_minor+:discount,
                    current_redemptions=current_redemptions+1,
                    status=case when used_discount_budget_minor+:discount>=total_discount_budget_minor
                    or current_redemptions+1>=maximum_redemptions then 'COMPLETED' else status end
                    where id=:campaign returning merchant_id,status"""
                ),
                {"discount": redemption["discount_minor"], "campaign": redemption["campaign_id"]},
            ).mappings().one()
            self.db.execute(
                text("update campaign_offers set status='REDEEMED' where id=:offer"),
                {"offer": redemption["offer_id"]},
            )
            self.db.execute(
                text(
                    """insert into campaign_events(campaign_id,merchant_id,event_type,actor_type,payload)
                    values(:campaign,:merchant,'CAMPAIGN_REDEEMED','PAYMENT_SERVICE',cast(:payload as jsonb))"""
                ),
                {
                    "campaign": redemption["campaign_id"],
                    "merchant": campaign_state["merchant_id"],
                    "payload": json.dumps({"transaction_id": str(transaction["id"]), "discount_minor": redemption["discount_minor"]}),
                },
            )
            if campaign_state["status"] == "COMPLETED":
                self.db.execute(
                    text(
                        """insert into campaign_events(campaign_id,merchant_id,event_type,actor_type,payload)
                        values(:campaign,:merchant,'CAMPAIGN_AUTO_STOPPED','PAYMENT_SERVICE',cast(:payload as jsonb))"""
                    ),
                    {
                        "campaign": redemption["campaign_id"],
                        "merchant": campaign_state["merchant_id"],
                        "payload": json.dumps({"reason": "BUDGET_OR_REDEMPTIONS_EXHAUSTED"}),
                    },
                )
        self.db.commit()
        return self._attempt(updated)

    def get_attempt(self, attempt_id: UUID) -> PaymentAttemptRecord:
        row = (
            self.db.execute(text("select * from payment_attempts where id=:id"), {"id": attempt_id})
            .mappings()
            .one()
        )
        return self._attempt(row)

    def get_attempt_by_order(self, order_id: str) -> PaymentAttemptRecord | None:
        row = (
            self.db.execute(
                text("select * from payment_attempts where razorpay_order_id=:order"),
                {"order": order_id},
            )
            .mappings()
            .one_or_none()
        )
        return self._attempt(row) if row else None

    def record_event_once(
        self, event_id: str, event_type: str, attempt_id: UUID | None, safe_payload: dict
    ) -> bool:
        row = self.db.execute(
            text(
                "insert into payment_provider_events(provider,provider_event_id,event_type,payment_attempt_id,payload_safe) values('RAZORPAY',:event,:type,:attempt,cast(:payload as jsonb)) on conflict(provider,provider_event_id) do nothing returning id"
            ),
            {
                "event": event_id,
                "type": event_type,
                "attempt": attempt_id,
                "payload": json.dumps(safe_payload),
            },
        ).scalar()
        return row is not None

    @staticmethod
    def _refund(row) -> RefundRecord:
        return RefundRecord(
            id=row["id"],
            payment_attempt_id=row["payment_attempt_id"],
            amount_minor=row["amount_minor"],
            currency=row["currency"],
            idempotency_key=row["idempotency_key"],
            status=RefundStatus(row["status"]),
            provider_refund_id=row.get("provider_refund_id"),
        )

    def claim_refund(
        self,
        attempt_id: UUID,
        user_id: UUID,
        amount_minor: int,
        reason: str,
        idempotency_key: str,
    ) -> tuple[RefundRecord, bool]:
        existing = (
            self.db.execute(
                text("select * from refunds where idempotency_key=:key"), {"key": idempotency_key}
            )
            .mappings()
            .one_or_none()
        )
        if existing:
            if existing["payment_attempt_id"] != attempt_id or existing["amount_minor"] != amount_minor:
                raise ValueError("Refund idempotency key conflicts with another request")
            return self._refund(existing), False
        attempt = (
            self.db.execute(
                text(
                    "select pa.* from payment_attempts pa join transactions t on t.id=pa.transaction_id "
                    "where pa.id=:attempt and t.user_id=:user for update"
                ),
                {"attempt": attempt_id, "user": user_id},
            )
            .mappings()
            .one_or_none()
        )
        if not attempt or attempt["status"] != "CAPTURED":
            raise PermissionError("Only the owner of a verified CAPTURED payment may request a refund")
        reserved = int(
            self.db.execute(
                text(
                    "select coalesce(sum(amount_minor),0) from refunds where payment_attempt_id=:attempt "
                    "and status in ('REQUESTED','PROCESSING','PROCESSED','UNKNOWN')"
                ),
                {"attempt": attempt_id},
            ).scalar_one()
        )
        if reserved + amount_minor > attempt["amount_minor"]:
            raise ValueError("Cumulative refund exceeds captured payment amount")
        row = (
            self.db.execute(
                text(
                    "insert into refunds(payment_attempt_id,user_id,amount_minor,currency,reason,idempotency_key,status) "
                    "values(:attempt,:user,:amount,:currency,:reason,:key,'REQUESTED') returning *"
                ),
                {
                    "attempt": attempt_id,
                    "user": user_id,
                    "amount": amount_minor,
                    "currency": attempt["currency"],
                    "reason": reason,
                    "key": idempotency_key,
                },
            )
            .mappings()
            .one()
        )
        self.db.commit()
        return self._refund(row), True

    def update_refund(
        self,
        refund_id: UUID,
        status: RefundStatus,
        provider_refund_id: str | None,
        safe_payload: dict,
    ) -> RefundRecord:
        row = (
            self.db.execute(
                text(
                    "update refunds set status=:status,provider_refund_id=coalesce(:provider,provider_refund_id),"
                    "provider_payload_safe=cast(:payload as jsonb),updated_at=now() where id=:id returning *"
                ),
                {
                    "status": status.value,
                    "provider": provider_refund_id,
                    "payload": json.dumps(safe_payload),
                    "id": refund_id,
                },
            )
            .mappings()
            .one()
        )
        self.db.commit()
        return self._refund(row)

    def get_refund(self, refund_id: UUID) -> RefundRecord:
        row = (
            self.db.execute(text("select * from refunds where id=:id"), {"id": refund_id})
            .mappings()
            .one()
        )
        return self._refund(row)

    def record_reconciliation(
        self,
        attempt_id: UUID,
        provider_status: str | None,
        amount_matches: bool,
        currency_matches: bool,
        resolution: str,
        safe_details: dict,
    ) -> None:
        observed = self.get_attempt(attempt_id).status.value
        self.db.execute(
            text(
                "insert into payment_reconciliations(payment_attempt_id,observed_status,provider_status,amount_matches,"
                "currency_matches,resolution,details_safe) values(:attempt,:observed,:provider,:amount,:currency,:resolution,cast(:details as jsonb))"
            ),
            {
                "attempt": attempt_id,
                "observed": observed,
                "provider": provider_status,
                "amount": amount_matches,
                "currency": currency_matches,
                "resolution": resolution,
                "details": json.dumps(safe_details),
            },
        )

    def commit(self) -> None:
        self.db.commit()
