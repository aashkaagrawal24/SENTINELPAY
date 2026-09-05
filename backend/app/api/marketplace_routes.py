import logging
from typing import Optional
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db.session import get_db_session
from app.services.marketplace_service import MarketplaceService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/marketplace", tags=["marketplace"])


class RankOffersRequest(BaseModel):
    offers: list[dict]
    quantity: int = Field(default=1, ge=1)
    budget_minor: Optional[int] = None


@router.get("/catalog")
def get_marketplace_catalog(
    query: str = Query(default="", description="Search keywords across brand, product name, description"),
    category: str = Query(default="", description="Filter by category"),
    in_stock_only: bool = Query(default=False, description="Filter for products currently in stock"),
    multi_seller_only: bool = Query(default=False, description="Filter for products sold by 2+ merchants"),
    negotiable_only: bool = Query(default=False, description="Filter for products with negotiation enabled"),
    bulk_only: bool = Query(default=False, description="Filter for products with bulk pricing available"),
    sort_by: str = Query(default="best_match", description="Sort by best_match, price_low, price_high, stock_high, sellers_high"),
    db: Session = Depends(get_db_session),
):
    """Global Marketplace endpoint aggregating active products and offers across all SentinelPay merchants."""
    return MarketplaceService.get_catalog(
        db,
        query=query,
        category=category,
        in_stock_only=in_stock_only,
        multi_seller_only=multi_seller_only,
        negotiable_only=negotiable_only,
        bulk_only=bulk_only,
        sort_by=sort_by,
    )


@router.get("/categories")
def get_categories(db: Session = Depends(get_db_session)):
    """Fetch distinct product categories currently available across the marketplace."""
    catalog = MarketplaceService.get_catalog(db)
    return {"categories": catalog.get("categories", [])}


@router.get("/products/{canonical_id}")
def get_canonical_product(canonical_id: str, db: Session = Depends(get_db_session)):
    """Fetch detailed canonical product info along with all merchant offers."""
    catalog = MarketplaceService.get_catalog(db)
    product = next((p for p in catalog["products"] if p["canonical_id"] == canonical_id), None)
    if not product:
        return {"error": "Product not found", "canonical_id": canonical_id}
    return product


@router.post("/rank-offers")
def rank_offers(body: RankOffersRequest):
    """Rank merchant offers based on fulfillment feasibility, pricing, and policy flexibility with explainable reasons."""
    return MarketplaceService.rank_offers(
        offers=body.offers,
        quantity=body.quantity,
        budget_minor=body.budget_minor,
    )
