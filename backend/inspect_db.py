import sys
from app.db.session import get_db_session
from sqlalchemy import text

db = next(get_db_session())
cols = db.execute(text("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'merchants'")).fetchall()
print("merchants columns:")
for c in cols:
    print(f"  {c[0]} ({c[1]})")

merchants = db.execute(text("select id, name, created_at from merchants")).fetchall()
print("\nMERCHANTS in DB:")
for m in merchants:
    print(f"  {m[0]} | {m[1]}")

products = db.execute(text("""
    select p.id, p.merchant_id, p.name, p.brand, p.category, p.base_price_minor, p.active, m.name,
           coalesce(sum(i.available_quantity - i.reserved_quantity), 0) as stock
    from merchant_products p
    join merchants m on m.id = p.merchant_id
    left join merchant_inventory i on i.product_id = p.id
    group by p.id, m.name
""")).fetchall()

print("\nPRODUCTS in DB:")
for p in products:
    print(f"  {p[0]} | Merchant: {p[7]} ({p[1]}) | {p[2]} | Brand: {p[3]} | Cat: {p[4]} | INR {p[5]/100} | active={p[6]} | stock={p[8]}")
