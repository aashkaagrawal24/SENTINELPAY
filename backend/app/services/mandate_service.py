import hashlib
import json
import secrets
from datetime import UTC, datetime, timedelta

from app.schemas.buyer import ParsedIntent


class MandateService:
    def authority(self, intent: ParsedIntent) -> dict:
        return {
            "product_scope": {"query": intent.product_query},
            "max_total_amount_minor": intent.max_budget_minor,
            "currency": intent.currency,
            "max_quantity": intent.quantity,
            "allowed_conditions": intent.allowed_conditions,
            "preferred_brands": intent.preferred_brands,
            "excluded_brands": intent.excluded_brands,
            "negotiation_allowed": intent.negotiation_allowed,
            "upsell_allowed": intent.upsell_allowed,
            "cross_sell_allowed": intent.cross_sell_allowed,
            "campaign_offer_allowed": intent.campaign_offer_allowed,
            "auto_purchase_allowed": False,
            "expires_at": (
                datetime.now(UTC) + timedelta(minutes=intent.mandate_expiry_minutes)
            ).isoformat(),
        }

    def hash(self, authority: dict) -> str:
        return hashlib.sha256(
            json.dumps(authority, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    def nonce(self) -> str:
        return secrets.token_hex(16)

    def verify_integrity(self, authority: dict, expected_hash: str) -> bool:
        return secrets.compare_digest(self.hash(authority), expected_hash)

    @staticmethod
    def ensure_active(
        status: str, expires_at: datetime, execution_count: int, max_executions: int
    ) -> None:
        if status != "ACTIVE":
            raise ValueError(f"Mandate is {status}")
        if expires_at <= datetime.now(UTC):
            raise ValueError("Mandate expired")
        if execution_count >= max_executions:
            raise ValueError("Mandate execution limit reached")

    @staticmethod
    def safe_summary(row: dict) -> dict:
        allowed = {
            "id",
            "product_scope",
            "max_total_amount_minor",
            "currency",
            "max_quantity",
            "allowed_conditions",
            "preferred_brands",
            "excluded_brands",
            "delivery_deadline",
            "negotiation_allowed",
            "upsell_allowed",
            "cross_sell_allowed",
            "campaign_offer_allowed",
            "auto_purchase_allowed",
            "expires_at",
            "status",
        }
        return {key: value for key, value in row.items() if key in allowed}
