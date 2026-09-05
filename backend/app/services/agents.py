import logging
from uuid import UUID

from sqlalchemy.orm import Session

from app.services.merchant_services import MerchantCatalogService

logger = logging.getLogger(__name__)


class MerchantAgent:
    """Exposes only buyer-safe catalog capabilities, never private policy internals."""

    def search(self, db: Session, query: str, merchant_id: UUID | None = None) -> list[dict]:
        logger.info("agent_tool_call tool=merchant_catalog_search merchant_id=%s", merchant_id)
        return MerchantCatalogService.public_catalog(db, query, merchant_id)


class BuyerAgent:
    """Ranks stored catalog candidates without receiving mandate mutation capability."""

    def __init__(self, merchant_agent: MerchantAgent):
        self.merchant_agent = merchant_agent

    def candidates(self, db: Session, parsed_intent, merchant_id: UUID | None = None) -> list[dict]:
        rows = self.merchant_agent.search(db, parsed_intent.product_query, merchant_id)
        budget = parsed_intent.max_budget_minor if parsed_intent.max_budget_minor is not None else 999999999
        allowed_conds = set(parsed_intent.allowed_conditions or [])
        excluded_brands = set(parsed_intent.excluded_brands or [])

        matches = [
            row
            for row in rows
            if row["current_price_minor"] <= budget
            and (not allowed_conds or row.get("condition") in allowed_conds)
            and row.get("brand") not in excluded_brands
        ]
        if not matches and rows:
            matches = [row for row in rows if row.get("brand") not in excluded_brands]

        # Calculate seller counts and other merchant offers for identical items
        # Group by normalized (brand, name)
        grouped_by_item: dict[str, list[dict]] = {}
        for r in rows:
            key = f"{(r.get('brand') or '').strip().lower()}::{r['name'].strip().lower()}"
            grouped_by_item.setdefault(key, []).append(r)

        # Sort matches by stock availability first, then lowest price
        matches.sort(key=lambda r: (-(1 if int(r.get("stock", 0)) > 0 else 0), r["current_price_minor"]))

        for row in matches:
            key = f"{(row.get('brand') or '').strip().lower()}::{row['name'].strip().lower()}"
            peers = grouped_by_item.get(key, [])
            seller_count = len({p["merchant_id"] for p in peers})
            other_offers = [
                {
                    "product_id": str(p["product_id"]),
                    "merchant_id": str(p["merchant_id"]),
                    "merchant_name": p.get("merchant_name") or "Verified Merchant",
                    "current_price_minor": p["current_price_minor"],
                    "currency": p.get("currency") or "INR",
                    "stock": int(p.get("stock", 0)),
                }
                for p in peers
                if str(p["product_id"]) != str(row["product_id"])
            ]

            m_name = row.get("merchant_name") or "Verified Merchant"
            stock = int(row.get("stock", 0))
            reasons = ["within_budget"]
            reasons.append(f"Seller: {m_name}")
            if stock > 0:
                reasons.append(f"{stock} units in stock")
            else:
                reasons.append("Out of stock")

            if seller_count > 1:
                reasons.append(f"Available from {seller_count} sellers")
            if row.get("negotiation_supported"):
                reasons.append("AI negotiation supported")

            row["seller_count"] = seller_count
            row["other_offers"] = other_offers
            row["why_matched"] = reasons
            row["provenance"] = "MERCHANT_CATALOG"
        return matches
