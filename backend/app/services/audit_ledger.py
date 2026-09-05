import hashlib
import json
from datetime import UTC, datetime
from typing import Any, ClassVar
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session
import asyncio

from app.services.event_dispatcher import dispatcher

ZERO_HASH = "0" * 64


class AuditLedgerService:
    EVENT_TYPES: ClassVar[set[str]] = {
        "INTENT_RECEIVED",
        "MANDATE_CREATED",
        "PRODUCT_DISCOVERED",
        "STRATEGY_SELECTED",
        "NEGOTIATION_STARTED",
        "COUNTEROFFER_RECEIVED",
        "UPSELL_OFFERED",
        "UPSELL_ACCEPTED",
        "CAMPAIGN_OPPORTUNITY_DETECTED",
        "CAMPAIGN_PROPOSED",
        "CAMPAIGN_APPROVED",
        "CAMPAIGN_STARTED",
        "CAMPAIGN_ASSIGNMENT_CREATED",
        "CAMPAIGN_OFFER_SERVED",
        "POLICY_VERIFIED",
        "CART_COMMITTED",
        "PAYMENT_ORDER_CREATED",
        "PAYMENT_EVENT_RECEIVED",
        "PAYMENT_CAPTURED",
        "PAYMENT_RECONCILED",
        "REFUND_REQUESTED",
        "REFUND_STATE_CHANGED",
        "RECEIPT_GENERATED",
        "SECURITY_DENIED",
        "SECURITY_FAILURE",
        "SECURITY_ATTACK_BLOCKED",
        "SECURITY_ATTACK_ALLOWED",
        "ADVANCED_EXTENSION_EVALUATED",
    }

    @staticmethod
    def canonical(payload: dict[str, Any]) -> str:
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)

    @classmethod
    def hashes(cls, previous_hash: str, payload: dict[str, Any]) -> tuple[str, str]:
        canonical = cls.canonical(payload)
        payload_hash = hashlib.sha256(canonical.encode()).hexdigest()
        current_hash = hashlib.sha256((previous_hash + canonical).encode()).hexdigest()
        return payload_hash, current_hash

    def append(
        self,
        db: Session,
        *,
        scope: str,
        event_type: str,
        actor: str,
        payload: dict[str, Any],
        user_id: UUID | None = None,
        merchant_id: UUID | None = None,
        transaction_id: UUID | None = None,
        session_id: UUID | None = None,
        metadata: dict[str, Any] | None = None,
        provenance_ids: list[str] | None = None,
    ) -> dict:
        if event_type not in self.EVENT_TYPES:
            raise ValueError(f"Unsupported audit event type: {event_type}")
        db.execute(text("select pg_advisory_xact_lock(hashtext(:scope))"), {"scope": scope})
        previous = (
            db.execute(
                text(
                    "select chain_sequence,current_event_hash from audit_events where chain_scope=:scope order by chain_sequence desc limit 1"
                ),
                {"scope": scope},
            )
            .mappings()
            .one_or_none()
        )
        previous_hash = previous["current_event_hash"] if previous else ZERO_HASH
        sequence = int(previous["chain_sequence"]) + 1 if previous else 1
        occurred_at = datetime.now(UTC)
        canonical_payload = {
            "event_type": event_type,
            "actor": actor,
            "occurred_at": occurred_at.isoformat(),
            "payload": payload,
        }
        payload_hash, current_hash = self.hashes(previous_hash, canonical_payload)
        row = (
            db.execute(
                text(
                    """insert into audit_events(user_id,merchant_id,transaction_id,session_id,event_type,actor,occurred_at,canonical_payload,payload_hash,previous_event_hash,current_event_hash,chain_scope,chain_sequence,metadata,provenance_ids)
                    values(:user_id,:merchant_id,:transaction_id,:session_id,:event_type,:actor,:occurred_at,cast(:payload as jsonb),:payload_hash,:previous_hash,:current_hash,:scope,:sequence,cast(:metadata as jsonb),cast(:provenance as jsonb)) returning *"""
                ),
                {
                    "user_id": user_id,
                    "merchant_id": merchant_id,
                    "transaction_id": transaction_id,
                    "session_id": session_id,
                    "event_type": event_type,
                    "actor": actor,
                    "occurred_at": occurred_at,
                    "payload": self.canonical(canonical_payload),
                    "payload_hash": payload_hash,
                    "previous_hash": previous_hash,
                    "current_hash": current_hash,
                    "scope": scope,
                    "sequence": sequence,
                    "metadata": json.dumps(metadata or {}, default=str),
                    "provenance": json.dumps(provenance_ids or []),
                },
            )
            .mappings()
            .one()
        )
        row_dict = dict(row)
        
        if merchant_id:
            evt_data = {
                "id": str(row_dict["id"]),
                "timestamp": int(occurred_at.timestamp() * 1000),
                "eventType": event_type,
                "description": f"Audit trace: {event_type} by {actor}",
                "status": "SUCCESS"
            }
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(dispatcher.publish(f"merchant_{merchant_id}", "AUDIT_EVENT", evt_data))
            except RuntimeError:
                # No running loop, probably in a sync test context without one
                pass
                
        return row_dict

    @classmethod
    def verify_rows(cls, rows: list[dict[str, Any]]) -> dict[str, Any]:
        previous_hash = ZERO_HASH
        expected_sequence = 1
        for row in rows:
            if row["chain_sequence"] != expected_sequence:
                return {"valid": False, "reason": "MISSING_LINK", "at_sequence": expected_sequence}
            payload = row["canonical_payload"]
            expected_payload, expected_current = cls.hashes(previous_hash, payload)
            if row["previous_event_hash"] != previous_hash:
                return {"valid": False, "reason": "PREVIOUS_HASH_MISMATCH", "at_sequence": expected_sequence}
            if row["payload_hash"] != expected_payload or row["current_event_hash"] != expected_current:
                return {"valid": False, "reason": "PAYLOAD_MUTATION", "at_sequence": expected_sequence}
            previous_hash = row["current_event_hash"]
            expected_sequence += 1
        return {"valid": True, "reason": "CHAIN_VALID", "events": len(rows), "head": previous_hash}

    def verify_chain(self, db: Session, scope: str) -> dict[str, Any]:
        rows = [
            dict(row)
            for row in db.execute(
                text("select * from audit_events where chain_scope=:scope order by chain_sequence"),
                {"scope": scope},
            ).mappings()
        ]
        return self.verify_rows(rows)
