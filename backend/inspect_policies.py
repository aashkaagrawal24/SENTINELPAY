from app.db.session import get_db_session
from sqlalchemy import text

db = next(get_db_session())
cols = db.execute(text("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'merchant_policies'")).fetchall()
print("merchant_policies columns:")
for c in cols:
    print(f"  {c[0]} ({c[1]})")

# Also check bulk policy tables if any
tables = db.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")).fetchall()
print("\nAll DB Tables:")
for t in tables:
    print(f"  {t[0]}")
