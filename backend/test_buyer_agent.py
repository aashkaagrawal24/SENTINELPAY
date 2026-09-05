from app.db.session import get_db_session
from app.services.agents import BuyerAgent, MerchantAgent
from pydantic import BaseModel
from typing import Optional, List

class MockIntent(BaseModel):
    product_query: str = "Vanilla Ice Cream Tub"
    max_budget_minor: Optional[int] = 20000
    allowed_conditions: Optional[List[str]] = None
    excluded_brands: Optional[List[str]] = None

db = next(get_db_session())
candidates = BuyerAgent(MerchantAgent()).candidates(db, MockIntent())
print("Found candidates:", len(candidates))
for c in candidates:
    m_name = c.get("merchant_name")
    p_name = c["name"]
    price = c["current_price_minor"] / 100
    stock = c.get("stock")
    sellers = c.get("seller_count")
    print(f"  Product: {p_name} | Merchant: {m_name} | Price: INR {price} | Stock: {stock} | Sellers: {sellers}")
    print(f"    Why: {c.get('why_matched')}")
    print(f"    Other offers: {c.get('other_offers')}")
