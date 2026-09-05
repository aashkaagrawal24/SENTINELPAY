import json
from sqlalchemy import create_engine, text
from app.core.config import get_settings

engine = create_engine(get_settings().supabase_database_url.get_secret_value())
with engine.connect() as conn:
    res = conn.execute(text("select failed_constraints from policy_evaluations order by created_at desc limit 1")).fetchone()
    print("FAILED CONSTRAINTS:", res[0] if res else None)
