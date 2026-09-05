import hashlib
import logging
from uuid import UUID, uuid5, NAMESPACE_DNS
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class MarketplaceService:
    """Canonical Marketplace Service aggregating active products from all merchants

    into cross-merchant canonical products and offers with AI ranking and
    explainability.
    """

    @classmethod
    def get_catalog(
        cls,
        db: Session,
        query: str = "",
        category: str = "",
        in_stock_only: bool = False,
        multi_seller_only: bool = False,
        negotiable_only: bool = False,
        bulk_only: bool = False,
        sort_by: str = "best_match",
    ) -> dict:
        """Fetches active products across all active merchants, groups identical items into

        canonical products with merchant offers, and returns filtered/sorted
        results.
        """
        # Fetch all active products with stock and merchant info
        sql = """
            SELECT 
                p.id as product_id,
                p.merchant_id,
                m.name as merchant_name,
                p.sku,
                p.name,
                p.brand,
                p.category,
                p.description,
                p.base_price_minor as current_price_minor,
                p.currency,
                p.condition,
                coalesce(sum(i.available_quantity - i.reserved_quantity), 0) as stock,
                case when coalesce(sum(i.available_quantity - i.reserved_quantity), 0) > 0 
                     then 'IN_STOCK' else 'OUT_OF_STOCK' end as inventory_status
            FROM merchant_products p
            JOIN merchants m ON m.id = p.merchant_id
            LEFT JOIN merchant_inventory i ON i.product_id = p.id
            WHERE p.active
            GROUP BY p.id, m.name
            ORDER BY p.name, m.name
        """
        raw_rows = [dict(r) for r in db.execute(text(sql)).mappings().fetchall()]

        # Collect merchant policies to annotate negotiation capabilities
        policies_sql = """
            SELECT merchant_id, scope, scope_reference, negotiation_enabled, 
                   maximum_discount_percent
            FROM merchant_policies
            WHERE status = 'ACTIVE'
              AND valid_from <= now()
              AND (valid_until IS NULL OR valid_until > now())
            ORDER BY case scope when 'PRODUCT' then 3 when 'CATEGORY' then 2 else 1 end desc, version desc
        """
        policy_rows = [dict(r) for r in db.execute(text(policies_sql)).mappings().fetchall()]

        # Collect bulk policy rules
        bulk_sql = """
            SELECT merchant_id, product_id, min_quantity, max_quantity, max_discount_percent
            FROM bulk_policy_rules
            WHERE status = 'ACTIVE' AND approved_by_merchant = TRUE
        """
        bulk_rows = [dict(r) for r in db.execute(text(bulk_sql)).mappings().fetchall()]

        # Map policies by (merchant_id, product_id, category)
        def find_policy(m_id, p_id, cat):
            for pol in policy_rows:
                if str(pol["merchant_id"]) == str(m_id):
                    scope = pol.get("scope")
                    ref = pol.get("scope_reference")
                    if scope == "PRODUCT" and str(ref) == str(p_id):
                        return pol
                    if scope == "CATEGORY" and str(ref).lower() == str(cat).lower():
                        return pol
                    if scope == "GLOBAL":
                        return pol
            return None

        def find_bulk_policy(m_id, p_id):
            for b in bulk_rows:
                if str(b["merchant_id"]) == str(m_id):
                    if b.get("product_id") is None or str(b.get("product_id")) == str(p_id):
                        return b
            return None

        # Build list of dynamic categories
        categories_set = set()
        for r in raw_rows:
            if r.get("category"):
                categories_set.add(r["category"].strip())
        categories = sorted(list(categories_set))

        # Filter raw rows by query if provided
        filtered_rows = []
        q_clean = (query or "").strip().lower()
        words = [w for w in q_clean.replace(",", " ").replace("-", " ").split() if len(w) > 1]

        for r in raw_rows:
            p_cat = (r.get("category") or "").strip()
            if category and p_cat.lower() != category.strip().lower():
                continue

            if words:
                text_to_search = f"{r['name']} {r.get('brand') or ''} {p_cat} {r.get('description') or ''}".lower()
                if not any(w in text_to_search for w in words):
                    continue

            filtered_rows.append(r)

        # Group rows into Canonical Products by normalized (brand, name)
        grouped: dict[str, dict] = {}
        for r in filtered_rows:
            brand_norm = (r.get("brand") or "Generic").strip().lower()
            name_norm = r["name"].strip().lower()
            group_key = f"{brand_norm}::{name_norm}"

            pol = find_policy(r["merchant_id"], r["product_id"], r.get("category"))
            b_pol = find_bulk_policy(r["merchant_id"], r["product_id"])
            
            neg_enabled = bool(pol and pol.get("negotiation_enabled"))
            max_disc = float(pol.get("maximum_discount_percent") or 10.0) if pol else 10.0
            
            bulk_min = int(b_pol.get("min_quantity") or 50) if b_pol else 50
            bulk_disc = float(b_pol.get("max_discount_percent") or 15.0) if b_pol else 15.0
            bulk_enabled = bool(b_pol is not None or r["stock"] >= 50)

            offer = {
                "product_id": str(r["product_id"]),
                "merchant_id": str(r["merchant_id"]),
                "merchant_name": r["merchant_name"],
                "sku": r.get("sku") or "SKU-GENERIC",
                "unit_price_minor": r["current_price_minor"],
                "currency": r["currency"] or "INR",
                "condition": r.get("condition") or "NEW",
                "stock": int(r["stock"]),
                "inventory_status": r["inventory_status"],
                "negotiation_enabled": neg_enabled,
                "max_discount_percent": max_disc,
                "bulk_enabled": bulk_enabled,
                "bulk_min_quantity": bulk_min,
                "bulk_discount_percent": bulk_disc,
            }

            if group_key not in grouped:
                canonical_id = hashlib.md5(group_key.encode("utf-8")).hexdigest()[:16]
                grouped[group_key] = {
                    "canonical_id": canonical_id,
                    "name": r["name"].strip(),
                    "brand": (r.get("brand") or "Generic").strip(),
                    "category": r.get("category") or "General",
                    "description": r.get("description") or "",
                    "offers": [],
                }

            grouped[group_key]["offers"].append(offer)

        # Assemble and calculate aggregated metrics for each canonical product
        canonical_products = []
        for p in grouped.values():
            offers = p["offers"]
            # Sort offers by price ascending
            offers.sort(key=lambda o: o["unit_price_minor"])

            prices = [o["unit_price_minor"] for o in offers]
            stocks = [o["stock"] for o in offers]
            min_price = min(prices)
            max_price = max(prices)
            total_stock = sum(stocks)
            seller_count = len({o["merchant_id"] for o in offers})
            neg_avail = any(o["negotiation_enabled"] for o in offers)
            bulk_avail = any(o["bulk_enabled"] for o in offers)

            # Apply additional flags
            if in_stock_only and total_stock <= 0:
                continue
            if multi_seller_only and seller_count < 2:
                continue
            if negotiable_only and not neg_avail:
                continue
            if bulk_only and not bulk_avail:
                continue

            best_offer = offers[0]
            canonical_products.append({
                "canonical_id": p["canonical_id"],
                "name": p["name"],
                "brand": p["brand"],
                "category": p["category"],
                "description": p["description"],
                "seller_count": seller_count,
                "min_price_minor": min_price,
                "max_price_minor": max_price,
                "starting_price_inr": round(min_price / 100, 2),
                "total_stock": total_stock,
                "best_offer": best_offer,
                "negotiation_available": neg_avail,
                "bulk_available": bulk_avail,
                "offers": offers,
            })

        # Sort canonical products
        if sort_by == "price_low":
            canonical_products.sort(key=lambda x: x["min_price_minor"])
        elif sort_by == "price_high":
            canonical_products.sort(key=lambda x: x["min_price_minor"], reverse=True)
        elif sort_by == "stock_high":
            canonical_products.sort(key=lambda x: x["total_stock"], reverse=True)
        elif sort_by == "sellers_high":
            canonical_products.sort(key=lambda x: x["seller_count"], reverse=True)
        else:
            # best_match: multi-sellers first, then in-stock, then title
            canonical_products.sort(key=lambda x: (-x["seller_count"], -(1 if x["total_stock"] > 0 else 0), x["name"]))

        return {
            "products": canonical_products,
            "categories": categories,
            "total_products": len(canonical_products),
            "total_offers": sum(p["seller_count"] for p in canonical_products),
        }

    @classmethod
    def rank_offers(
        cls, offers: list[dict], quantity: int = 1, budget_minor: Optional[int] = None
    ) -> dict:
        """Ranks a list of merchant offers for a specific purchase requirement

        (retail or bulk) with verifiable, fact-based AI explanations.
        """
        if not offers:
            return {"ranked_offers": [], "recommended_offer": None, "explanation": "No offers available"}

        min_price = min(o["unit_price_minor"] for o in offers)

        evaluated = []
        for o in offers:
            stock = int(o.get("stock", 0))
            price = int(o.get("unit_price_minor", 0))
            can_fulfill = stock >= quantity
            reasons = []

            # 1. Fulfillment check
            if can_fulfill:
                if quantity > 1:
                    reasons.append(f"Can fulfill all {quantity} units (Stock: {stock})")
                else:
                    reasons.append(f"In stock and ready to ship ({stock} units available)")
            else:
                reasons.append(f"Insufficient stock: only {stock} available ({quantity} requested)")

            # 2. Price competitiveness
            if price == min_price:
                reasons.append(f"Best starting price in marketplace at INR {price / 100:,.2f}/unit")
            else:
                diff_pct = round(((price - min_price) / min_price) * 100, 1)
                reasons.append(f"Starting price: INR {price / 100:,.2f}/unit (+{diff_pct}% vs lowest)")

            # 3. Budget sufficiency
            if budget_minor is not None:
                if price <= budget_minor:
                    reasons.append(f"Within buyer authorized budget of INR {budget_minor / 100:,.2f}")
                else:
                    reasons.append(f"Above authorized budget by INR {(price - budget_minor) / 100:,.2f}")

            # 4. Policy flexibility
            if o.get("negotiation_enabled"):
                reasons.append(f"Autonomous negotiation enabled (up to {o.get('max_discount_percent', 10)}% flexibility)")

            if o.get("bulk_enabled") and quantity >= int(o.get("bulk_min_quantity", 50)):
                reasons.append(f"Qualifies for bulk tier ({o.get('bulk_discount_percent', 15)}% discount)")

            evaluated.append({
                **o,
                "can_fulfill": can_fulfill,
                "reasons": reasons,
                "sort_rank": (0 if can_fulfill else 1, price, -stock),
            })

        evaluated.sort(key=lambda x: x["sort_rank"])

        for i, item in enumerate(evaluated):
            item["rank"] = i + 1
            item["is_recommended"] = (i == 0)

        recommended = evaluated[0]
        explanation = (
            f"Recommended {recommended['merchant_name']} at INR {recommended['unit_price_minor'] / 100:,.2f}/unit: "
            + "; ".join(recommended["reasons"][:3])
        )

        return {
            "ranked_offers": evaluated,
            "recommended_offer": recommended,
            "explanation": explanation,
        }
