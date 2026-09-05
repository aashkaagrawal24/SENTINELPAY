from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session


class MerchantService:
    @staticmethod
    def role(db: Session, merchant_id: UUID, user_id: UUID) -> str:
        role = db.execute(
            text("select role from merchant_users where merchant_id=:m and user_id=:u"),
            {"m": merchant_id, "u": user_id},
        ).scalar()
        if not role:
            raise HTTPException(403, "Cross-merchant access denied")
        return str(role)

    @classmethod
    def require_operator(cls, db: Session, merchant_id: UUID, user_id: UUID) -> None:
        if cls.role(db, merchant_id, user_id) not in {"OWNER", "ADMIN"}:
            raise HTTPException(403, "OWNER or ADMIN role required")


class MerchantCatalogService:
    PUBLIC_FIELDS = "p.id product_id,p.merchant_id,m.name merchant_name,p.name,p.brand,p.category,p.description,p.base_price_minor current_price_minor,p.currency,p.condition,p.metadata,p.updated_at last_updated,coalesce(sum(i.available_quantity-i.reserved_quantity),0) stock"

    @classmethod
    def public_catalog(
        cls, db: Session, query: str = "", merchant_id: UUID | None = None
    ) -> list[dict]:
        merchant_filter = "and p.merchant_id=:merchant_id" if merchant_id else ""
        clean_query = (query or "").strip()
        words = [w.strip() for w in clean_query.replace(",", " ").replace("-", " ").split() if len(w.strip()) > 1]
        
        products = []
        if words:
            and_clauses = []
            params = {"merchant_id": merchant_id}
            for i, w in enumerate(words):
                and_clauses.append(f"(p.name ilike :w{i} or p.category ilike :w{i} or coalesce(p.brand,'') ilike :w{i} or coalesce(p.description,'') ilike :w{i})")
                params[f"w{i}"] = f"%{w}%"
            where_and = " and ".join(and_clauses)
            sql_and = f"""select {cls.PUBLIC_FIELDS},case when coalesce(sum(i.available_quantity-i.reserved_quantity),0)>0 then 'IN_STOCK' else 'OUT_OF_STOCK' end inventory_status from merchant_products p join merchants m on m.id=p.merchant_id left join merchant_inventory i on i.product_id=p.id where p.active and ({where_and}) {merchant_filter} group by p.id, m.name order by p.name"""
            products = [dict(row) for row in db.execute(text(sql_and), params).mappings()]
            
            if not products:
                where_or = " or ".join(and_clauses)
                sql_or = f"""select {cls.PUBLIC_FIELDS},case when coalesce(sum(i.available_quantity-i.reserved_quantity),0)>0 then 'IN_STOCK' else 'OUT_OF_STOCK' end inventory_status from merchant_products p join merchants m on m.id=p.merchant_id left join merchant_inventory i on i.product_id=p.id where p.active and ({where_or}) {merchant_filter} group by p.id, m.name order by p.name"""
                products = [dict(row) for row in db.execute(text(sql_or), params).mappings()]

        if not products:
            sql_all = f"""select {cls.PUBLIC_FIELDS},case when coalesce(sum(i.available_quantity-i.reserved_quantity),0)>0 then 'IN_STOCK' else 'OUT_OF_STOCK' end inventory_status from merchant_products p join merchants m on m.id=p.merchant_id left join merchant_inventory i on i.product_id=p.id where p.active {merchant_filter} group by p.id, m.name order by p.name"""
            products = [dict(row) for row in db.execute(text(sql_all), {"merchant_id": merchant_id}).mappings()]
        for product in products:
            product["variants"] = [
                dict(row)
                for row in db.execute(
                    text(
                        "select id,variant_key,name,attributes,price_override_minor from product_variants where product_id=:p order by variant_key"
                    ),
                    {"p": product["product_id"]},
                ).mappings()
            ]
            product["relationships"] = [
                dict(row)
                for row in db.execute(
                    text(
                        "select relationship_type,target_product_id,priority,weight from merchant_relationships where source_product_id=:p and active order by priority desc"
                    ),
                    {"p": product["product_id"]},
                ).mappings()
            ]
            policy = db.execute(
                text(
                    "select negotiation_enabled from merchant_policies where merchant_id=:m and status='ACTIVE' and valid_from<=now() and (valid_until is null or valid_until>now()) and (scope='GLOBAL' or (scope='CATEGORY' and scope_reference=:category) or (scope='PRODUCT' and scope_reference=:product)) order by case scope when 'PRODUCT' then 3 when 'CATEGORY' then 2 else 1 end desc,version desc limit 1"
                ),
                {
                    "m": product["merchant_id"],
                    "category": product["category"],
                    "product": str(product["product_id"]),
                },
            ).scalar()
            product.update(
                {
                    "negotiation_supported": bool(policy),
                    "delivery_capability": "MERCHANT_DEFINED",
                    "active_offers": [],
                    "checkout_capability": "SECURITY_KERNEL_REQUIRED",
                    "warranty": product["metadata"].get("warranty")
                    if product["metadata"]
                    else None,
                    "returns": product["metadata"].get("returns") if product["metadata"] else None,
                }
            )
        return products


class MerchantInventoryService:
    @staticmethod
    def available(db: Session, product_id: UUID) -> int:
        return int(
            db.execute(
                text(
                    "select coalesce(sum(available_quantity-reserved_quantity),0) from merchant_inventory where product_id=:p"
                ),
                {"p": product_id},
            ).scalar_one()
        )


class MerchantPolicyService:
    @staticmethod
    def select_active(
        policies: list[dict], product_id: str, category: str, at: datetime | None = None
    ) -> dict | None:
        now = at or datetime.now(UTC)
        matches = [
            p
            for p in policies
            if p["status"] == "ACTIVE"
            and p["valid_from"] <= now
            and (p.get("valid_until") is None or p["valid_until"] > now)
            and (
                p["scope"] == "GLOBAL"
                or p["scope"] == "PRODUCT"
                and p.get("scope_reference") == product_id
                or p["scope"] == "CATEGORY"
                and p.get("scope_reference") == category
            )
        ]
        rank = {"GLOBAL": 1, "CATEGORY": 2, "PRODUCT": 3}
        return max(matches, key=lambda p: (rank[p["scope"]], p["version"])) if matches else None
