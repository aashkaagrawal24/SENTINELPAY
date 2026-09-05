import os
import sys
import uuid
from datetime import datetime, timezone
import random
from sqlalchemy import text

# Add the parent directory to the path so we can import from app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import get_db_session

def get_platforms_for_category(category):
    cat_lower = (category or "").lower()
    
    # Base platforms for all categories
    platforms = [
        {"name": "Amazon", "base_url": "https://www.amazon.in/s?k=", "min_multiplier": 1.01, "max_multiplier": 1.05},
        {"name": "Flipkart", "base_url": "https://www.flipkart.com/search?q=", "min_multiplier": 1.02, "max_multiplier": 1.06},
        {"name": "OLX", "base_url": "https://www.olx.in/items/q-", "min_multiplier": 0.85, "max_multiplier": 0.95} # Negotiable P2P
    ]
    
    if cat_lower in ["headphones", "laptops", "electronics", "accessories"]:
        platforms.extend([
            {"name": "Croma", "base_url": "https://www.croma.com/searchB?q=", "min_multiplier": 1.03, "max_multiplier": 1.08},
            {"name": "Reliance Digital", "base_url": "https://www.reliancedigital.in/search?q=", "min_multiplier": 1.02, "max_multiplier": 1.07},
            {"name": "Vijay Sales", "base_url": "https://www.vijaysales.com/search-result?q=", "min_multiplier": 1.04, "max_multiplier": 1.09},
        ])
    elif cat_lower in ["footwear", "clothes", "apparel", "fashion"]:
        platforms.extend([
            {"name": "Myntra", "base_url": "https://www.myntra.com/", "min_multiplier": 1.01, "max_multiplier": 1.06},
            {"name": "Ajio", "base_url": "https://www.ajio.com/search/?text=", "min_multiplier": 0.98, "max_multiplier": 1.05},
        ])
        
    return platforms

def seed():
    print("Starting seed of external_offer_snapshots...")
    session_gen = get_db_session()
    db = next(session_gen)
    
    try:
        # Get all merchant products to seed
        products = db.execute(text("SELECT name, base_price_minor, category FROM merchant_products")).fetchall()
        print(f"Found {len(products)} products.")
        
        run_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        
        # Insert a dummy feature run to satisfy FK constraint
        # Get a real user_id to satisfy the feature run's user_id foreign key constraint
        user = db.execute(text("SELECT id FROM profiles LIMIT 1")).fetchone()
        user_id = user[0] if user else uuid.uuid4()
        
        db.execute(text("""
            INSERT INTO advanced_feature_runs (id, user_id, feature_key, status, input_safe, result_safe, metrics, baseline, created_at)
            VALUES (:id, :user_id, 'market_intelligence_seed', 'SUCCESS', 'true'::jsonb, 'true'::jsonb, '{}', '{}', :created_at)
        """), {"id": run_id, "user_id": user_id, "created_at": now})
        
        # Get a valid provenance_id
        prov = db.execute(text("SELECT id FROM provenance_records LIMIT 1")).fetchone()
        prov_id = prov[0] if prov else None
        
        for p in products:
            product_name = p[0]
            price_minor = p[1]
            category = p[2]
            
            if not price_minor:
                continue
                
            norm_key = product_name.lower()
            
            # Clear existing for this product so we can re-run safely
            db.execute(text(f"DELETE FROM external_offer_snapshots WHERE normalized_product_key = '{norm_key}'"))
            
            platforms = get_platforms_for_category(category)
            
            for platform in platforms:
                platform_price = int(price_minor * random.uniform(platform["min_multiplier"], platform["max_multiplier"]))
                
                # Special URL encoding for search queries
                query_param = product_name.replace(' ', '%20' if 'croma' in platform["base_url"] else '+')
                source_url = f"{platform['base_url']}{query_param}"
                
                cap = "NEGOTIATION_ONLY" if platform["name"] == "OLX" else "PUBLIC_SCOUT"
                
                db.execute(text(f"""
                    INSERT INTO external_offer_snapshots 
                    (id, run_id, connector, capability, external_offer_id, normalized_product_key, title, price_minor, currency, checkout_capability, source_url, fetched_at, freshness_seconds, provenance_id)
                    VALUES ('{uuid.uuid4()}', '{run_id}', '{platform["name"]}', '{cap}', '{platform['name'][:3].upper()}-{uuid.uuid4().hex[:8]}', '{norm_key}', '{product_name.replace("'", "''")}', {platform_price}, 'INR', 'UNSUPPORTED', '{source_url.replace("'", "''")}', '{now}', 3600, '{prov_id}')
                """))
            
        db.commit()
        print("Successfully seeded external offers for all categories.")
        
    except Exception as e:
        print(f"Error: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    seed()
