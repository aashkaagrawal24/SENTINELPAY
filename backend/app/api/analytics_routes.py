from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthenticatedUser, get_current_user
from app.db.session import get_db_session
from app.services.analytics_services import RevenueAnalyticsService, SyntheticEvaluationService
from app.services.merchant_services import MerchantService

router = APIRouter(prefix="/api")


def window(body: dict) -> tuple[datetime, datetime]:
    end = (
        datetime.fromisoformat(body["end"])
        if body.get("end")
        else datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        + timedelta(days=1)
    )
    start = (
        datetime.fromisoformat(body["start"])
        if body.get("start")
        else end - timedelta(days=30)
    )
    if start >= end:
        raise HTTPException(422, "Analytics start must precede end")
    return start, end


@router.post("/merchants/{merchant_id}/analytics/refresh")
def refresh_analytics(
    merchant_id: UUID,
    body: dict,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    MerchantService.require_operator(db, merchant_id, user.id)
    scope = str(body.get("data_scope", "REAL")).upper()
    if scope not in {"REAL", "SIMULATED"}:
        raise HTTPException(422, "data_scope must be REAL or SIMULATED")
    start, end = window(body)
    campaigns = list(
        db.execute(
            text("select id from campaigns where merchant_id=:merchant"),
            {"merchant": merchant_id},
        ).scalars()
    )
    campaign_metrics = [
        RevenueAnalyticsService.refresh_campaign(db, campaign, start, end, scope)
        for campaign in campaigns
    ]
    merchant_metric = RevenueAnalyticsService.refresh_merchant(
        db, merchant_id, start, end, scope
    )
    db.commit()
    return {
        "merchant": merchant_metric,
        "campaigns": campaign_metrics,
        "data_scope": scope,
        "refunds": "NOT_IMPLEMENTED_EXCLUDED_FROM_METRICS",
    }


@router.get("/merchants/{merchant_id}/analytics")
def get_analytics(
    merchant_id: UUID,
    data_scope: str = "REAL",
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    MerchantService.role(db, merchant_id, user.id)
    scope = data_scope.upper()
    if scope not in {"REAL", "SIMULATED"}:
        raise HTTPException(422, "data_scope must be REAL or SIMULATED")
    merchant = db.execute(
        text(
            "select * from merchant_metrics where merchant_id=:merchant and data_scope=:scope order by period_end desc limit 1"
        ),
        {"merchant": merchant_id, "scope": scope},
    ).mappings().one_or_none()
    campaigns = [
        dict(row)
        for row in db.execute(
            text(
                """select cm.*,c.name,c.status,c.objective,c.control_percentage,c.discount_type,c.discount_value,
                c.total_discount_budget_minor,c.used_discount_budget_minor,c.reserved_discount_budget_minor,
                c.maximum_redemptions,c.current_redemptions,c.reserved_redemptions,c.stop_conditions,
                co.trigger_type opportunity_trigger,cp.products
                from campaign_metrics cm join campaigns c on c.id=cm.campaign_id
                left join campaign_opportunities co on co.id=c.opportunity_id
                left join lateral (select jsonb_agg(product_id) products from campaign_products where campaign_id=c.id) cp on true
                where c.merchant_id=:merchant and cm.data_scope=:scope
                and cm.window_end=(select max(latest.window_end) from campaign_metrics latest where latest.campaign_id=cm.campaign_id and latest.data_scope=:scope)
                order by c.created_at desc"""
            ),
            {"merchant": merchant_id, "scope": scope},
        ).mappings()
    ]
    return {
        "merchant": dict(merchant) if merchant else None,
        "campaigns": campaigns,
        "data_scope": scope,
        "labels": {
            "attributed": "ATTRIBUTED CAMPAIGN REVENUE",
            "controlled": "CONTROLLED EXPERIMENT ESTIMATE",
        },
        "source_tables": [
            "agent_sessions",
            "transactions",
            "payment_attempts",
            "campaign_assignments",
            "campaign_offers",
            "campaign_redemptions",
            "upsell_events",
            "cross_sell_events",
            "negotiation_sessions",
        ],
        "refunds": "NOT_IMPLEMENTED_EXCLUDED_FROM_METRICS",
    }


@router.post("/merchants/{merchant_id}/analytics/simulate")
def simulate_evaluation(
    merchant_id: UUID,
    body: dict,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    MerchantService.require_operator(db, merchant_id, user.id)
    count = int(body.get("count", 250))
    if not 100 <= count <= 1000:
        raise HTTPException(422, "Synthetic evaluation count must be 100-1000")
    campaign = db.execute(
        text(
            "select id,control_percentage from campaigns where id=:campaign and merchant_id=:merchant"
        ),
        {"campaign": body["campaign_id"], "merchant": merchant_id},
    ).mappings().one_or_none()
    if not campaign:
        raise HTTPException(404, "Owned campaign not found")
    generated = SyntheticEvaluationService.generate(
        db,
        merchant_id,
        campaign["id"],
        count,
        int(body.get("seed", 42)),
        int(campaign["control_percentage"]),
    )
    return {
        "generated": generated,
        "provenance": "SIMULATED",
        "real_metrics_contaminated": False,
    }
