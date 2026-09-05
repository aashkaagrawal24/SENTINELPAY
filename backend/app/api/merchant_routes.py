from fastapi.responses import StreamingResponse
from app.services.event_dispatcher import dispatcher
from fastapi import Request
import io
import json
import re
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import text
from sqlalchemy.orm import Session

import docx
import pypdf

from app.auth.dependencies import AuthenticatedUser, get_current_user
from app.db.session import get_db_session
from app.schemas.merchant import (
    InventoryInput,
    PolicyInput,
    ProductInput,
    ProductPatch,
    RelationshipInput,
)
from app.services.merchant_services import MerchantCatalogService, MerchantService
from app.services.pricing_intelligence_service import PricingIntelligenceService

router = APIRouter(prefix="/api")


@router.post("/merchants")
def create_merchant(
    body: dict,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    if not body.get("name"):
        raise HTTPException(422, "Merchant name required")
    row = (
        db.execute(
            text("insert into merchants(name) values(:name) returning id,name,created_at"),
            {"name": body["name"]},
        )
        .mappings()
        .one()
    )
    db.execute(
        text("insert into merchant_users(merchant_id,user_id,role) values(:m,:u,'OWNER')"),
        {"m": row["id"], "u": user.id},
    )
    db.commit()
    return dict(row)


@router.post("/merchants/seed")
def seed_demo_merchant(
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    # Ensure profile exists
    db.execute(
        text("insert into profiles(id, display_name) values(:u, 'Merchant Owner') on conflict do nothing"),
        {"u": user.id},
    )
    
    # Check if user already owns a merchant
    existing = db.execute(
        text("select m.id, m.name from merchants m join merchant_users mu on mu.merchant_id=m.id where mu.user_id=:u limit 1"),
        {"u": user.id},
    ).mappings().one_or_none()
    
    if existing:
        merchant_id = existing["id"]
    else:
        m_row = db.execute(
            text("insert into merchants(name) values('Sentinel Audio Demo') returning id"),
        ).mappings().one()
        merchant_id = m_row["id"]
        db.execute(
            text("insert into merchant_users(merchant_id,user_id,role) values(:m,:u,'OWNER') on conflict do nothing"),
            {"m": merchant_id, "u": user.id},
        )
    
    # Seed 3 Products
    products_to_seed = [
        ("SONY-XM4", "Sony WH-1000XM4", "Sony", "Headphones", "Premium noise-cancelling headphones", 1999900, {"color": "Midnight Blue"}),
        ("SONY-XM5", "Sony WH-1000XM5", "Sony", "Headphones", "Flagship noise-cancelling headphones", 2449900, {"color": "Silver"}),
        ("CASE-XM", "Protective Case", "Sentinel", "Accessories", "Protective travel case", 49900, {"size": "Standard"}),
    ]
    
    product_ids = {}
    for sku, name, brand, cat, desc, price, attrs in products_to_seed:
        p_row = db.execute(
            text("select id from merchant_products where merchant_id=:m and sku=:sku"),
            {"m": merchant_id, "sku": sku},
        ).mappings().one_or_none()
        
        if not p_row:
            p_row = db.execute(
                text("insert into merchant_products(merchant_id,sku,name,brand,category,description,condition,base_price_minor,currency,active,metadata) values(:m,:sku,:name,:brand,:cat,:desc,'NEW',:price,'INR',true,'{}') returning id"),
                {"m": merchant_id, "sku": sku, "name": name, "brand": brand, "cat": cat, "desc": desc, "price": price},
            ).mappings().one()
            db.execute(
                text("insert into product_variants(product_id,variant_key,name,attributes) values(:pid,'default','Default',cast(:attrs as jsonb))"),
                {"pid": p_row["id"], "attrs": json.dumps(attrs)},
            )
            # Inventory
            qty = 50 if sku == "CASE-XM" else 20
            db.execute(
                text("insert into merchant_inventory(merchant_id,product_id,available_quantity,reserved_quantity) values(:m,:pid,:qty,0) on conflict do nothing"),
                {"m": merchant_id, "pid": p_row["id"], "qty": qty},
            )
        product_ids[sku] = p_row["id"]
        
    # Seed Policy for XM4
    xm4_id = product_ids.get("SONY-XM4")
    if xm4_id:
        has_policy = db.execute(
            text("select 1 from merchant_policies where merchant_id=:m and scope_reference=:pid"),
            {"m": merchant_id, "pid": str(xm4_id)},
        ).scalar()
        if not has_policy:
            db.execute(
                text("""insert into merchant_policies(merchant_id,scope,scope_reference,base_price_minor,minimum_sale_price_minor,maximum_discount_percent,negotiation_enabled,max_negotiation_rounds,upsell_enabled,cross_sell_enabled,status,version)
                values(:m,'PRODUCT',:pid,1999900,1850000,7.50,true,3,true,true,'ACTIVE',1)"""),
                {"m": merchant_id, "pid": str(xm4_id)},
            )
            
    # Seed Policy for XM5
    xm5_id = product_ids.get("SONY-XM5")
    if xm5_id:
        has_policy5 = db.execute(
            text("select 1 from merchant_policies where merchant_id=:m and scope_reference=:pid"),
            {"m": merchant_id, "pid": str(xm5_id)},
        ).scalar()
        if not has_policy5:
            db.execute(
                text("""insert into merchant_policies(merchant_id,scope,scope_reference,base_price_minor,minimum_sale_price_minor,maximum_discount_percent,negotiation_enabled,max_negotiation_rounds,upsell_enabled,cross_sell_enabled,status,version)
                values(:m,'PRODUCT',:pid,2449900,2249000,8.00,true,3,true,true,'ACTIVE',1)"""),
                {"m": merchant_id, "pid": str(xm5_id)},
            )
            
    # Seed Relationships
    case_id = product_ids.get("CASE-XM")
    if xm4_id and case_id:
        db.execute(
            text("insert into merchant_relationships(merchant_id,source_product_id,target_product_id,relationship_type,priority) values(:m,:src,:tgt,'ACCESSORY',10) on conflict do nothing"),
            {"m": merchant_id, "src": xm4_id, "tgt": case_id},
        )
    if xm4_id and xm5_id:
        db.execute(
            text("insert into merchant_relationships(merchant_id,source_product_id,target_product_id,relationship_type,priority) values(:m,:src,:tgt,'UPSELL',5) on conflict do nothing"),
            {"m": merchant_id, "src": xm4_id, "tgt": xm5_id},
        )
        
    db.commit()
    return {"merchant_id": merchant_id, "status": "SEEDED", "products": list(product_ids.keys())}



@router.get("/merchants")
def list_merchants(
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    rows = db.execute(
        text("""
            select m.id, m.name, mu.role, m.created_at
            from merchants m
            join merchant_users mu on mu.merchant_id = m.id
            where mu.user_id = :u
            order by m.created_at desc
        """),
        {"u": user.id}
    ).mappings().fetchall()
    return {"merchants": [dict(r) for r in rows]}


@router.get("/merchants/{merchant_id}")
def get_merchant(
    merchant_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    role = MerchantService.role(db, merchant_id, user.id)
    row = (
        db.execute(
            text("select id,name,created_at,updated_at from merchants where id=:m"),
            {"m": merchant_id},
        )
        .mappings()
        .one()
    )
    return {**dict(row), "role": role}


@router.post("/merchants/{merchant_id}/products")
def create_product(
    merchant_id: UUID,
    body: ProductInput,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    MerchantService.require_operator(db, merchant_id, user.id)
    
    # Check for existing SKU
    existing = db.execute(
        text("select id from merchant_products where merchant_id=:merchant_id and sku=:sku"),
        {"merchant_id": merchant_id, "sku": body.sku},
    ).mappings().one_or_none()
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Product with SKU '{body.sku}' already exists. Please use a unique SKU (e.g. {body.sku}-2).",
        )

    values = body.model_dump(exclude={"variants", "metadata"})
    row = (
        db.execute(
            text(
                "insert into merchant_products(merchant_id,sku,name,brand,category,description,condition,base_price_minor,currency,active,metadata) values(:merchant_id,:sku,:name,:brand,:category,:description,:condition,:base_price_minor,:currency,:active,cast(:metadata as jsonb)) returning id"
            ),
            {"merchant_id": merchant_id, "metadata": json.dumps(body.metadata), **values},
        )
        .mappings()
        .one()
    )
    for variant in body.variants:
        db.execute(
            text(
                "insert into product_variants(product_id,variant_key,name,attributes,price_override_minor) values(:product_id,:variant_key,:name,cast(:attributes as jsonb),:price_override_minor)"
            ),
            {
                "product_id": row["id"],
                "attributes": json.dumps(variant.attributes),
                **variant.model_dump(exclude={"attributes"}),
            },
        )
    # Auto-initialize inventory
    db.execute(
        text("insert into merchant_inventory(merchant_id,product_id,available_quantity,reserved_quantity) values(:m,:pid,50,0) on conflict do nothing"),
        {"m": merchant_id, "pid": row["id"]},
    )
    # Auto-initialize policy
    db.execute(
        text("""
            insert into merchant_policies(
                merchant_id, scope, scope_reference, base_price_minor,
                minimum_sale_price_minor, maximum_discount_percent,
                negotiation_enabled, max_negotiation_rounds,
                upsell_enabled, cross_sell_enabled, valid_from, status, version
            ) values (
                :m, 'PRODUCT', cast(:pid as text), :base_price,
                :min_price, 25, true, 3, true, true, now(), 'ACTIVE', 1
            )
        """),
        {
            "m": merchant_id, 
            "pid": row["id"], 
            "base_price": body.base_price_minor,
            "min_price": int(body.base_price_minor * 0.75)
        }
    )
    db.commit()
    return {"id": row["id"], "sku": body.sku, "name": body.name}



@router.get("/merchants/{merchant_id}/products")
def list_products(
    merchant_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    MerchantService.role(db, merchant_id, user.id)
    return [
        dict(row)
        for row in db.execute(
            text("""
                select p.*, i.available_quantity, i.reserved_quantity, i.reorder_threshold, i.target_threshold
                from merchant_products p
                left join merchant_inventory i on i.product_id = p.id
                where p.merchant_id=:m
                order by p.created_at
            """),
            {"m": merchant_id},
        ).mappings()
    ]


@router.get("/merchants/{merchant_id}/products/{product_id}")
def get_product(
    merchant_id: UUID,
    product_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    MerchantService.role(db, merchant_id, user.id)
    row = (
        db.execute(
            text("select * from merchant_products where id=:p and merchant_id=:m"),
            {"p": product_id, "m": merchant_id},
        )
        .mappings()
        .one_or_none()
    )
    if not row:
        raise HTTPException(404, "Product not found")
    return dict(row)


@router.patch("/merchants/{merchant_id}/products/{product_id}")
def patch_product(
    merchant_id: UUID,
    product_id: UUID,
    body: ProductPatch,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    MerchantService.require_operator(db, merchant_id, user.id)
    values = body.model_dump(exclude_none=True)
    if values:
        assignments = ",".join(f"{key}=:{key}" for key in values)
        result = db.execute(
            text(
                f"update merchant_products set {assignments} where id=:id and merchant_id=:merchant_id"
            ),
            {"id": product_id, "merchant_id": merchant_id, **values},
        )
        if not result.rowcount:
            raise HTTPException(404, "Product not found")
        db.commit()
    return get_product(merchant_id, product_id, user, db)


@router.put("/merchants/{merchant_id}/inventory/{product_id}")
def update_inventory(
    merchant_id: UUID,
    product_id: UUID,
    body: InventoryInput,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    MerchantService.require_operator(db, merchant_id, user.id)
    
    res = db.execute(
        text(
            "update merchant_inventory set available_quantity=:available_quantity, reserved_quantity=:reserved_quantity, reorder_threshold=:reorder_threshold, target_threshold=:target_threshold, updated_at=now() where merchant_id=:m and product_id=:p"
        ),
        {"m": merchant_id, "p": product_id, **body.model_dump()}
    )
    if res.rowcount == 0:
        db.execute(
            text(
                "insert into merchant_inventory(merchant_id,product_id,available_quantity,reserved_quantity,reorder_threshold,target_threshold) values(:m,:p,:available_quantity,:reserved_quantity,:reorder_threshold,:target_threshold)"
            ),
            {"m": merchant_id, "p": product_id, **body.model_dump()}
        )
    db.commit()
    return {"product_id": product_id, **body.model_dump()}


@router.post("/merchants/{merchant_id}/policies")
def create_policy(
    merchant_id: UUID,
    body: PolicyInput,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    MerchantService.require_operator(db, merchant_id, user.id)
    version = db.execute(
        text(
            "select coalesce(max(version),0)+1 from merchant_policies where merchant_id=:m and scope=:s and scope_reference is not distinct from :r"
        ),
        {"m": merchant_id, "s": body.scope, "r": body.scope_reference},
    ).scalar_one()
    fields = body.model_dump()
    columns = ",".join(fields)
    placeholders = ",".join(f":{key}" for key in fields)
    row = (
        db.execute(
            text(
                f"insert into merchant_policies(merchant_id,{columns},version) values(:merchant_id,{placeholders},:version) returning id,version,status"
            ),
            {"merchant_id": merchant_id, "version": version, **fields},
        )
        .mappings()
        .one()
    )
    db.commit()
    return dict(row)


@router.put("/merchants/{merchant_id}/policies/{policy_id}")
def update_policy(
    merchant_id: UUID,
    policy_id: UUID,
    body: PolicyInput,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    MerchantService.require_operator(db, merchant_id, user.id)
    fields = body.model_dump()
    assignments = ",".join(f"{key}=:{key}" for key in fields)
    result = db.execute(
        text(
            f"update merchant_policies set {assignments}, updated_at=now() where id=:id and merchant_id=:merchant_id"
        ),
        {"id": policy_id, "merchant_id": merchant_id, **fields},
    )
    if not result.rowcount:
        raise HTTPException(404, "Policy not found")
    db.commit()
    return {"id": policy_id, **fields}


@router.get("/merchants/{merchant_id}/policies")
def list_policies(
    merchant_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    MerchantService.role(db, merchant_id, user.id)
    return [
        dict(row)
        for row in db.execute(
            text("select * from merchant_policies where merchant_id=:m order by created_at desc"),
            {"m": merchant_id},
        ).mappings()
    ]


@router.post("/merchants/{merchant_id}/relationships")
def create_relationship(
    merchant_id: UUID,
    body: RelationshipInput,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    MerchantService.require_operator(db, merchant_id, user.id)
    row = (
        db.execute(
            text(
                "insert into merchant_relationships(merchant_id,source_product_id,target_product_id,relationship_type,priority,weight,active) select :m,:source_product_id,:target_product_id,:relationship_type,:priority,:weight,:active where exists(select 1 from merchant_products where id=:source_product_id and merchant_id=:m) and exists(select 1 from merchant_products where id=:target_product_id and merchant_id=:m) returning id"
            ),
            {"m": merchant_id, **body.model_dump()},
        )
        .mappings()
        .one_or_none()
    )
    if not row:
        raise HTTPException(403, "Products must belong to the merchant")
    db.commit()
    return dict(row)


@router.get("/merchants/{merchant_id}/catalog")
def merchant_catalog(
    merchant_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    MerchantService.role(db, merchant_id, user.id)
    return MerchantCatalogService.public_catalog(db, merchant_id=merchant_id)


@router.post("/agent/catalog/search")
def agent_search(body: dict, db: Session = Depends(get_db_session)):
    return MerchantCatalogService.public_catalog(
        db, str(body.get("query", "")), body.get("merchant_id")
    )


@router.get("/agent/products/{product_id}")
def agent_product(product_id: UUID, db: Session = Depends(get_db_session)):
    rows = MerchantCatalogService.public_catalog(db)
    product = next((row for row in rows if row["product_id"] == product_id), None)
    if not product:
        raise HTTPException(404, "Product not found")
    return product


@router.get("/agent/products/{product_id}/inventory")
def agent_inventory(product_id: UUID, db: Session = Depends(get_db_session)):
    available = db.execute(
        text(
            "select coalesce(sum(available_quantity-reserved_quantity),0)>0 from merchant_inventory where product_id=:p"
        ),
        {"p": product_id},
    ).scalar_one()
    return {"product_id": product_id, "availability": "IN_STOCK" if available else "OUT_OF_STOCK"}


@router.get("/agent/products/{product_id}/offers")
def agent_offers(product_id: UUID, db: Session = Depends(get_db_session)):
    offers = [
        dict(row)
        for row in db.execute(
            text(
                """select c.id campaign_id,c.name,c.campaign_type,c.objective,c.discount_type,
                c.discount_value,c.max_discount_per_order_minor,c.end_time expires_at
                from campaigns c join campaign_products cp on cp.campaign_id=c.id
                where cp.product_id=:product and c.status='ACTIVE' and c.start_time<=now() and c.end_time>now()"""
            ),
            {"product": product_id},
        ).mappings()
    ]
    return {
        "product_id": product_id,
        "active_offers": offers,
        "eligibility": "BUYER_MANDATE_AND_CART_REQUIRED",
    }


def parse_raw_text_to_products(text_content: str):
    text_content = text_content.strip()
    if not text_content:
        return []

    # 1. Try JSON
    if text_content.startswith("{") or text_content.startswith("["):
        try:
            data = json.loads(text_content)
            items = data if isinstance(data, list) else [data]
            products = []
            for idx, it in enumerate(items):
                sku = str(it.get("sku") or f"SKU-IMPORT-{idx+1}")
                name = str(it.get("name") or it.get("product_name") or f"Imported Product {idx+1}")
                brand = str(it.get("brand") or "Generic")
                cat = str(it.get("category") or "General")
                price = float(it.get("price") or it.get("base_price") or 999)
                floor = float(it.get("floor_price") or it.get("min_price") or round(price * 0.9))
                stock = int(it.get("stock") or it.get("available_quantity") or 50)
                color = str(it.get("color") or it.get("variant") or "Standard")
                desc = str(it.get("description") or f"Verified {name}")
                products.append({
                    "sku": sku, "name": name, "brand": brand, "category": cat,
                    "price": price, "floor_price": floor, "stock": stock,
                    "color": color, "description": desc
                })
            return products
        except Exception:
            pass

    # 2. Key-Value Blocks (separated by '---' or double newlines)
    blocks = re.split(r"\n\s*---\s*\n|\n\s*\n(?=[A-Za-z0-9_-]+:)", text_content)
    products = []

    for i, block in enumerate(blocks):
        lines = block.splitlines()
        kv = {}
        for line in lines:
            if ":" in line:
                k, v = line.split(":", 1)
                k_norm = re.sub(r"[\s_-]", "", k).lower()
                kv[k_norm] = v.strip()

        if any(k in kv for k in ["name", "productname", "sku", "price", "baseprice"]):
            name = kv.get("name") or kv.get("productname") or f"Imported Item {i+1}"
            sku_cand = kv.get("sku") or f"SKU-{re.sub(r'[^A-Z0-9]', '', name.upper())[:6]}-{i+1}"
            brand = kv.get("brand") or kv.get("make") or "Generic"
            cat = kv.get("category") or kv.get("type") or "General"
            raw_p = kv.get("price") or kv.get("baseprice") or kv.get("mrp") or "999"
            clean_p = re.sub(r"[^\d.]", "", raw_p)
            price = float(clean_p) if clean_p else 999.0
            raw_f = kv.get("floorprice") or kv.get("minprice") or ""
            clean_f = re.sub(r"[^\d.]", "", raw_f)
            floor = float(clean_f) if clean_f else round(price * 0.9)
            raw_qty = kv.get("stock") or kv.get("qty") or kv.get("quantity") or "50"
            clean_qty = re.sub(r"\D", "", raw_qty)
            stock = int(clean_qty) if clean_qty else 50
            color = kv.get("color") or kv.get("variant") or "Standard"
            desc = kv.get("description") or kv.get("desc") or f"Agent-verified {name}"

            products.append({
                "sku": sku_cand, "name": name, "brand": brand, "category": cat,
                "price": price, "floor_price": floor, "stock": stock,
                "color": color, "description": desc
            })

    # 3. Line-by-line fallback for unformatted docs, invoices, price sheets
    if not products:
        lines = [l.strip() for l in text_content.splitlines() if l.strip()]
        for idx, line in enumerate(lines):
            price_match = re.search(r"(?:₹|rs\.?|inr|\$)\s*([\d,]+(?:\.\d+)?)", line, re.IGNORECASE)
            if price_match:
                price_str = price_match.group(1).replace(",", "")
                try:
                    price = float(price_str)
                    name_cand = re.sub(r"(?:₹|rs\.?|inr|\$)\s*[\d,]+(?:\.\d+)?", "", line, flags=re.IGNORECASE).strip(" -:\t")
                    if len(name_cand) > 3:
                        products.append({
                            "sku": f"DOC-{idx+1:03d}",
                            "name": name_cand,
                            "brand": "Generic",
                            "category": "General",
                            "price": price,
                            "floor_price": round(price * 0.9),
                            "stock": 50,
                            "color": "Standard",
                            "description": f"Extracted from line: {line}"
                        })
                except Exception:
                    continue

    return products


@router.post("/merchants/parse-document")
async def parse_merchant_document(
    file: UploadFile = File(...),
):
    try:
        content_bytes = await file.read()
        filename = (file.filename or "").lower()
        extracted_text = ""

        if filename.endswith(".pdf") or file.content_type == "application/pdf":
            try:
                reader = pypdf.PdfReader(io.BytesIO(content_bytes))
                pages_text = []
                for p in reader.pages:
                    text_page = p.extract_text()
                    if text_page:
                        pages_text.append(text_page)
                extracted_text = "\n".join(pages_text)
            except Exception as e:
                raise HTTPException(400, f"Error reading PDF: {str(e)}")

        elif filename.endswith(".docx") or "wordprocessingml" in (file.content_type or ""):
            try:
                doc = docx.Document(io.BytesIO(content_bytes))
                extracted_text = "\n".join([p.text for p in doc.paragraphs if p.text])
            except Exception as e:
                raise HTTPException(400, f"Error reading DOCX: {str(e)}")

        else:
            # Fallback text decoder
            try:
                extracted_text = content_bytes.decode("utf-8")
            except UnicodeDecodeError:
                extracted_text = content_bytes.decode("latin-1", errors="ignore")

        products = parse_raw_text_to_products(extracted_text)
        return {
            "filename": file.filename,
            "extracted_text": extracted_text,
            "products": products,
            "count": len(products),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, f"Failed to parse document: {str(e)}")


@router.get("/merchants/{merchant_id}/dashboard-stats")
def dashboard_stats(
    merchant_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    MerchantService.role(db, merchant_id, user.id)
    
    # Active Products
    products_count = db.execute(
        text("select count(*) from merchant_products where merchant_id=:m"),
        {"m": merchant_id},
    ).scalar() or 0

    # Total Revenue (real)
    total_revenue_minor = db.execute(
        text("select coalesce(sum(amount_minor), 0) from revenue_ledger where merchant_id=:m"),
        {"m": merchant_id},
    ).scalar() or 0

    # Orders Count (real)
    orders_count = db.execute(
        text("select count(distinct t.id) from transactions t join carts c on t.cart_id = c.id where c.merchant_id=:m and t.status='SUCCESS'"),
        {"m": merchant_id},
    ).scalar() or 0

    # Unique Buyer Sessions (based on carts created recently, or orders?)
    sessions_count = db.execute(
        text("select count(distinct id) from carts where merchant_id=:m"),
        {"m": merchant_id},
    ).scalar() or 0

    # Active Campaigns
    campaigns_count = db.execute(
        text("select count(*) from merchant_policies where merchant_id=:m and status='ACTIVE'"),
        {"m": merchant_id},
    ).scalar() or 0
    
    conv_rate = "0.0%"
    if sessions_count > 0:
        conv_rate = f"{round((orders_count / sessions_count) * 100, 1)}%"

    return {
        "metrics": {
            "totalRevenue": int(total_revenue_minor / 100),
            "activeSessions": sessions_count,
            "conversionRate": conv_rate,
            "activeCampaigns": campaigns_count
        }
    }


@router.get("/merchants/{merchant_id}/events/stream")
async def events_stream(
    merchant_id: UUID,
    request: Request,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    MerchantService.role(db, merchant_id, user.id)
    return StreamingResponse(
        dispatcher.event_generator(f"merchant_{merchant_id}"),
        media_type="text/event-stream"
    )

@router.get("/merchants/{merchant_id}/agent-activity")
def agent_activity(
    merchant_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    MerchantService.role(db, merchant_id, user.id)
    
    rows = db.execute(
        text("""
            select a.id, a.event_type, a.occurred_at, a.actor, a.payload_hash
            from audit_events a
            where a.merchant_id=:m or 
                  a.transaction_id in (select t.id from transactions t join carts c on t.cart_id=c.id where c.merchant_id=:m)
            order by a.occurred_at desc
            limit 50
        """),
        {"m": merchant_id}
    ).mappings().fetchall()
    
    events = []
    for r in rows:
        events.append({
            "id": str(r["id"]),
            "timestamp": int(r["occurred_at"].timestamp() * 1000),
            "eventType": r["event_type"],
            "description": f"Audit trace: {r['event_type']} by {r['actor']}",
            "status": "SUCCESS"
        })
        
    return {"events": events}


@router.get("/merchants/{merchant_id}/orders")
def get_orders(
    merchant_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    MerchantService.role(db, merchant_id, user.id)
    
    rows = db.execute(
        text("""
            select t.id, t.status as txn_status, t.order_type, t.bulk_rfq_id,
                   pa.amount_minor, pa.status as pmt_status, t.created_at, p.name, p.sku,
                   coalesce(ci.quantity, 1) as quantity,
                   coalesce(ci.unit_price_minor, pa.amount_minor) as unit_price_minor
            from transactions t
            join carts c on t.cart_id = c.id
            left join payment_attempts pa on pa.transaction_id = t.id
            left join cart_items ci on ci.cart_id = c.id
            left join merchant_products p on p.id = ci.product_id
            where c.merchant_id=:m
            order by t.created_at desc
            limit 100
        """),
        {"m": merchant_id}
    ).mappings().fetchall()
    
    orders = []
    for r in rows:
        orders.append({
            "id": str(r["id"]),
            "product": r["name"] or "Unknown Product",
            "sku": r["sku"] or "UNKNOWN",
            "amount": (r["amount_minor"] or 0) / 100,
            "status": "COMPLETED" if r["pmt_status"] == "CAPTURED" else "PROCESSING" if r["pmt_status"] else r["txn_status"],
            "date": int(r["created_at"].timestamp() * 1000),
            # New bulk fields
            "order_type": r.get("order_type") or "RETAIL",
            "bulk_rfq_id": str(r["bulk_rfq_id"]) if r.get("bulk_rfq_id") else None,
            "quantity": int(r["quantity"]),
            "unit_price_inr": round(int(r["unit_price_minor"] or 0) / 100, 2) if r.get("unit_price_minor") else None,
        })
        
    return {"orders": orders}



@router.get("/merchants/{merchant_id}/revenue")
def get_revenue(
    merchant_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    MerchantService.role(db, merchant_id, user.id)
    
    # Aggregate total revenue and attribution in one go
    rows = db.execute(
        text("""
            select attribution_type, coalesce(sum(amount_minor), 0) as amt, count(id) as cnt
            from revenue_ledger 
            where merchant_id=:m
            group by attribution_type
        """),
        {"m": merchant_id}
    ).mappings().fetchall()

    total_minor = sum(r["amt"] for r in rows)
    total_orders = sum(r["cnt"] for r in rows)

    ai_revenue_minor = sum(r["amt"] for r in rows if r["attribution_type"] == "AGENT_NEGOTIATED")
    campaign_revenue_minor = sum(r["amt"] for r in rows if r["attribution_type"] == "CAMPAIGN_INFLUENCED")
    bulk_negotiated_minor = sum(r["amt"] for r in rows if r["attribution_type"] == "AGENT_NEGOTIATED_BULK")
    direct_bulk_minor = sum(r["amt"] for r in rows if r["attribution_type"] == "DIRECT_BULK")

    total_bulk_minor = bulk_negotiated_minor + direct_bulk_minor
    total_retail_minor = total_minor - total_bulk_minor

    bulk_orders = sum(r["cnt"] for r in rows if r["attribution_type"] in ("AGENT_NEGOTIATED_BULK", "DIRECT_BULK"))
    retail_orders = total_orders - bulk_orders
    
    # Calculate percentages for the frontend
    def pct(amt):
        return round((amt / max(1, total_minor)) * 100, 1)

    agent_pct = pct(ai_revenue_minor)
    campaign_pct = pct(campaign_revenue_minor)
    upsell_pct = pct(sum(r["amt"] for r in rows if r["attribution_type"] == "UPSELL_CROSS_SELL"))
    direct_pct = pct(sum(r["amt"] for r in rows if r["attribution_type"] == "DIRECT_PURCHASE"))
    bulk_pct = pct(total_bulk_minor)

    return {
        # Existing keys — unchanged for backward compat
        "totalRevenue": int(total_minor / 100),
        "aiRevenue": int(ai_revenue_minor / 100),
        "campaignRevenue": int(campaign_revenue_minor / 100),
        "aov": int(total_minor / 100 / max(1, total_orders)),
        "attribution": {
            "agentNegotiated": agent_pct,
            "campaignInfluenced": campaign_pct,
            "upsell": upsell_pct,
            "direct": direct_pct,
            "agentNegotiatedBulk": pct(bulk_negotiated_minor),
            "directBulk": pct(direct_bulk_minor),
        },
        # New bulk-specific breakdown
        "bulk": {
            "totalRevenue": int(total_bulk_minor / 100),
            "negotiatedRevenue": int(bulk_negotiated_minor / 100),
            "directRevenue": int(direct_bulk_minor / 100),
            "orders": int(bulk_orders),
            "avgOrderValue": int(total_bulk_minor / 100 / max(1, bulk_orders)),
            "revenuePercent": bulk_pct,
        },
        "retail": {
            "totalRevenue": int(total_retail_minor / 100),
            "orders": int(retail_orders),
            "avgOrderValue": int(total_retail_minor / 100 / max(1, retail_orders)),
        },
    }


@router.get("/merchants/{merchant_id}/market-demand")
def get_market_demand(
    merchant_id: UUID,
    limit: int = 50,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    """Return the top buyer searches that the merchant currently has no stock for.

    Sorted by search_count descending so the hottest missed opportunities appear first.
    Estimated price is returned in both minor units and human-readable rupees.
    """
    MerchantService.role(db, merchant_id, user.id)
    rows = db.execute(
        text(
            """select id, product_query, estimated_price_minor, currency, search_count, last_searched_at, created_at
               from market_demand
               where merchant_id = :merchant_id
               order by search_count desc, last_searched_at desc
               limit :limit"""
        ),
        {"merchant_id": merchant_id, "limit": min(limit, 100)},
    ).mappings().all()

    return {
        "merchant_id": str(merchant_id),
        "total_missed_searches": len(rows),
        "demands": [
            {
                **dict(row),
                "id": str(row["id"]),
                "estimated_price_inr": round(row["estimated_price_minor"] / 100, 2)
                if row["estimated_price_minor"]
                else None,
                "last_searched_at": row["last_searched_at"].isoformat() if row["last_searched_at"] else None,
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            }
            for row in rows
        ],
    }


@router.delete("/merchants/{merchant_id}/market-demand/{demand_id}")
def dismiss_market_demand(
    merchant_id: UUID,
    demand_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    """Dismiss a market demand entry once the merchant has acted on it (e.g. added the product)."""
    MerchantService.role(db, merchant_id, user.id)
    result = db.execute(
        text("delete from market_demand where id=:id and merchant_id=:m"),
        {"id": demand_id, "m": merchant_id},
    )
    if not result.rowcount:
        raise HTTPException(404, "Demand entry not found")
    db.commit()
    return {"id": str(demand_id), "status": "DISMISSED"}


@router.get("/merchants/{merchant_id}/pricing-intelligence")
def get_pricing_intelligence(
    merchant_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    """5-Engine Autonomous Pricing & Policy Intelligence for merchant inventory."""
    MerchantService.role(db, merchant_id, user.id)
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

    evaluated_products = []
    total_pressure = 0.0
    excess_count = 0
    total_potential_profit = 0.0

    for p in products_raw:
        item = PricingIntelligenceService.evaluate_product(db, merchant_id, dict(p))
        evaluated_products.append(item)
        pressure = item["inventory_pressure"]
        total_pressure += pressure
        if item["has_excess_inventory"]:
            excess_count += 1
        total_potential_profit += item["recommended_policy"]["expected_total_profit_inr"]

    avg_pressure = round(total_pressure / max(1, len(evaluated_products)), 2)

    return {
        "summary": {
            "total_products": len(evaluated_products),
            "excess_inventory_products": excess_count,
            "average_inventory_pressure": avg_pressure,
            "potential_expected_profit_inr": round(total_potential_profit, 2),
        },
        "products": evaluated_products,
    }


@router.post("/merchants/{merchant_id}/pricing-intelligence/simulate")
def simulate_custom_pricing(
    merchant_id: UUID,
    body: dict,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    """Interactive re-simulation when a merchant modifies policy parameters."""
    MerchantService.role(db, merchant_id, user.id)
    return PricingIntelligenceService.resimulate_custom(
        base_price_minor=int(body.get("base_price_minor") or 0),
        cost_price_minor=int(body.get("cost_price_minor") or 0),
        available_quantity=int(body.get("available_quantity") or 0),
        forecast_30d_demand=int(body.get("forecast_30d_demand") or 10),
        category=str(body.get("category") or "General"),
        custom_discount_percent=float(body.get("discount_percent") or 0),
        custom_duration_days=int(body.get("duration_days") or 5),
        custom_order_limit=int(body.get("order_limit") or 100),
    )


@router.post("/merchants/{merchant_id}/pricing-intelligence/apply")
def apply_pricing_intelligence_policy(
    merchant_id: UUID,
    body: dict,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    """Commits an approved AI policy or merchant-edited proposal as an immutable version."""
    MerchantService.require_operator(db, merchant_id, user.id)
    product_id = body.get("product_id")
    if not product_id:
        raise HTTPException(400, "product_id is required")

    discount_percent = float(body.get("discount_percent") or 0)
    base_price_minor = int(body.get("base_price_minor") or 0)
    floor_price_minor = int(body.get("floor_price_minor") or 0)
    order_limit = int(body.get("order_limit") or 100)
    max_discount_minor = max(0, base_price_minor - floor_price_minor)
    total_budget_minor = max_discount_minor * order_limit

    version = db.execute(
        text(
            "select coalesce(max(version), 0) + 1 from merchant_policies where merchant_id = :m and scope = 'PRODUCT' and scope_reference = :r"
        ),
        {"m": merchant_id, "r": str(product_id)},
    ).scalar_one()

    row = (
        db.execute(
            text(
                """
                insert into merchant_policies (
                    merchant_id, scope, scope_reference, base_price_minor,
                    minimum_sale_price_minor, maximum_discount_percent,
                    campaign_discount_limit_percent, campaign_budget_limit_minor,
                    minimum_margin_percent, negotiation_enabled, max_negotiation_rounds,
                    upsell_enabled, cross_sell_enabled, valid_from, status, version
                ) values (
                    :merchant_id, 'PRODUCT', :scope_reference, :base_price_minor,
                    :minimum_sale_price_minor, :maximum_discount_percent,
                    :campaign_discount_limit_percent, :campaign_budget_limit_minor,
                    18.0, true, 3,
                    true, true, now(), 'ACTIVE', :version
                ) returning id, version, status
                """
            ),
            {
                "merchant_id": merchant_id,
                "scope_reference": str(product_id),
                "base_price_minor": base_price_minor,
                "minimum_sale_price_minor": floor_price_minor,
                "maximum_discount_percent": discount_percent,
                "campaign_discount_limit_percent": discount_percent,
                "campaign_budget_limit_minor": total_budget_minor,
                "version": version,
            },
        )
        .mappings()
        .one()
    )

    db.commit()
    return dict(row)

