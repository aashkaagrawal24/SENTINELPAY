from uuid import UUID
from app.db.session import get_db_session
from app.services.pricing_intelligence_service import PricingIntelligenceService
from sqlalchemy import text

db = next(get_db_session())
m_id = UUID('c9cbee91-ec6c-466f-a18a-9cdfbe0ecb9e')
prod = db.execute(
    text("select p.*, coalesce(i.available_quantity,0) as available_quantity, coalesce(i.reserved_quantity,0) as reserved_quantity from merchant_products p left join merchant_inventory i on i.product_id=p.id where p.merchant_id=:m limit 1"),
    {'m': m_id}
).mappings().first()
res = PricingIntelligenceService.evaluate_product(db, m_id, dict(prod))
print('EVALUATION SUCCESS:')
print('Product:', res['product_name'])
print('Category:', res['category'])
print('Base Price:', res['base_price_inr'])
print('Cost Price:', res['cost_price_inr'])
print('Inventory:', res['available_quantity'])
print('Pressure:', res['inventory_pressure'])
print('Recommended Discount:', res['recommended_policy']['recommended_discount_percent'], '%')
print('Expected Profit:', res['recommended_policy']['expected_total_profit_inr'])
print('\nSimulation Matrix:')
for row in res['simulation_matrix']:
    print(f"  {row['discount_percent']}% -> Price ₹{row['new_price_inr']} | Sales {row['predicted_sales']} | Profit ₹{row['expected_total_profit_inr']} | Cleared {row['stock_cleared_percent']}% {'<-- OPTIMAL' if row['is_optimal'] else ''}")
print('\nWhy:', res['recommended_policy']['why_reason'][:150])
