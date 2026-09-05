import json
from app.db.session import get_db_session
from app.services.pricing_intelligence_service import PricingIntelligenceService
from sqlalchemy import text

db = next(get_db_session())
merchants = db.execute(text("select id from merchants limit 1")).fetchall()
if not merchants:
    print("No merchants")
    exit(1)
merchant_id = merchants[0][0]

products_raw = db.execute(
    text(
        """
        select p.*, coalesce(i.available_quantity, 0) as available_quantity, coalesce(i.reserved_quantity, 0) as reserved_quantity
        from merchant_products p
        left join merchant_inventory i on i.product_id = p.id
        where p.merchant_id = :m and p.active
        order by coalesce(i.available_quantity, 0) desc, p.created_at
        """
    ),
    {"m": merchant_id},
).mappings().fetchall()

for p in products_raw:
    item = PricingIntelligenceService.evaluate_product(db, merchant_id, dict(p))
    print(f"Product ID: {item['product_id']}, Name: {item['product_name']}, Category: {item['category']}")
