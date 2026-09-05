from app.db.session import get_db_session
from app.services.marketplace_service import MarketplaceService

db = next(get_db_session())
catalog = MarketplaceService.get_catalog(db)

print("TOTAL CANONICAL PRODUCTS:", catalog["total_products"])
print("TOTAL OFFERS:", catalog["total_offers"])
print("CATEGORIES:", catalog["categories"])
print("\nSAMPLE PRODUCTS:")
for p in catalog["products"][:5]:
    print(f"- {p['name']} (Brand: {p['brand']}, Cat: {p['category']}) | Sellers: {p['seller_count']} | Starting: INR {p['starting_price_inr']} | Total Stock: {p['total_stock']}")
    for o in p["offers"]:
        print(f"    * Merchant: {o['merchant_name']} | Price: INR {o['unit_price_minor']/100} | Stock: {o['stock']} | Neg: {o['negotiation_enabled']} | Bulk: {o['bulk_enabled']}")

# Test Ranking: Vanilla Ice Cream for 500 units
vanilla = next((p for p in catalog["products"] if "vanilla" in p["name"].lower()), None)
if vanilla:
    print("\nRANKING TEST FOR VANILLA (500 units):")
    ranked = MarketplaceService.rank_offers(vanilla["offers"], quantity=500)
    print("Explanation:", ranked["explanation"])
    for r in ranked["ranked_offers"]:
        print(f"  Rank #{r['rank']} | {r['merchant_name']} | Price: INR {r['unit_price_minor']/100} | Stock: {r['stock']} | Can fulfill: {r['can_fulfill']}")
        for reason in r["reasons"]:
            print(f"    - {reason}")
