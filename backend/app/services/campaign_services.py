import json
from datetime import UTC, datetime, timedelta
from typing import ClassVar
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas.campaign import OpportunityMetrics


class OpportunityScore:
    WEIGHTS: ClassVar[dict[str, float]] = {
        "inventory_pressure": 0.30,
        "conversion_gap": 0.25,
        "demand_signal": 0.20,
        "margin_room": 0.15,
        "historical_lift": 0.10,
    }

    @classmethod
    def calculate(
        cls, metrics: OpportunityMetrics, weights: dict[str, float] | None = None
    ) -> tuple[float, list[str]]:
        selected_weights = weights or cls.WEIGHTS
        total_weight = sum(selected_weights.values()) or 1
        score = (
            sum(getattr(metrics, key) * weight for key, weight in selected_weights.items())
            / total_weight
        )
        reasons = []
        if metrics.inventory_pressure >= 0.6:
            reasons.append("EXCESS_INVENTORY")
        if metrics.conversion_gap >= 0.5:
            reasons.append("HIGH_INTEREST_LOW_CONVERSION")
        if metrics.abandoned_carts > 0:
            reasons.append("ABANDONED_CARTS")
        if metrics.demand_signal >= 0.4:
            reasons.append("REPEATED_DEMAND")
        if metrics.margin_room >= 0.05:
            reasons.append("POLICY_MARGIN_ROOM")
        if metrics.historical_lift > 0:
            reasons.append("HISTORICAL_GROWTH_ACCEPTANCE")
        return round(min(1.0, score), 5), reasons or ["INSUFFICIENT_SIGNAL"]


class CampaignOpportunityService:
    @staticmethod
    def _rows(db: Session, merchant_id: UUID, inventory_threshold: int) -> list[dict]:
        return [
            dict(row)
            for row in db.execute(
                text(
                    """
                    select p.id product_id,p.base_price_minor,
                      (select greatest(coalesce(sum(i.available_quantity-i.reserved_quantity),0),0) from merchant_inventory i where i.product_id=p.id) available_quantity,
                      (select count(*) from audit_events ae where ae.merchant_id=p.merchant_id and ae.event_type='PRODUCT_VIEW' and ae.created_at>=now()-interval '7 days') product_views,
                      (select count(distinct t.id) from cart_items ci join carts c on c.id=ci.cart_id join transactions t on t.cart_id=c.id where ci.product_id=p.id and t.status='SUCCESS') completed_transactions,
                      (select count(distinct c.id) from cart_items ci join carts c on c.id=ci.cart_id where ci.product_id=p.id and c.status in ('DRAFT','CART_READY') and c.updated_at<now()-interval '30 minutes') abandoned_carts,
                      (select count(*) from agent_sessions s where s.merchant_id=p.merchant_id and s.started_at>=now()-interval '7 days') demand_sessions,
                      (select count(*) from upsell_events ue where ue.source_product_id=p.id and ue.accepted)+(select count(*) from cross_sell_events ce where ce.source_product_id=p.id and ce.accepted) accepted_growth_events,
                      coalesce((select (coalesce(mp.base_price_minor,p.base_price_minor)-mp.minimum_sale_price_minor)::numeric/nullif(coalesce(mp.base_price_minor,p.base_price_minor),0) from merchant_policies mp where mp.merchant_id=p.merchant_id and mp.status='ACTIVE' and mp.valid_from<=now() and (mp.valid_until is null or mp.valid_until>now()) and (mp.scope='GLOBAL' or mp.scope='PRODUCT' and mp.scope_reference=p.id::text or mp.scope='CATEGORY' and mp.scope_reference=p.category) order by case mp.scope when 'PRODUCT' then 3 when 'CATEGORY' then 2 else 1 end desc,mp.version desc limit 1),0) margin_room
                    from merchant_products p
                    where p.merchant_id=:merchant and p.active
                    """
                ),
                {"merchant": merchant_id, "threshold": inventory_threshold},
            ).mappings()
        ]

    @classmethod
    def scan(
        cls,
        db: Session,
        merchant_id: UUID,
        trigger_type: str,
        inventory_threshold: int = 15,
        weights: dict[str, float] | None = None,
    ) -> list[dict]:
        created = []
        for row in cls._rows(db, merchant_id, inventory_threshold):
            views = int(row["product_views"])
            completed = int(row["completed_transactions"])
            abandoned = int(row["abandoned_carts"])
            sessions = int(row["demand_sessions"])
            growth = int(row["accepted_growth_events"])
            available = int(row["available_quantity"])
            interest = views + abandoned + sessions
            metrics = OpportunityMetrics(
                inventory_pressure=min(1, available / max(1, inventory_threshold)),
                conversion_gap=min(1, max(0, interest - completed) / max(1, interest)),
                demand_signal=min(1, (views + sessions + abandoned * 2) / 10),
                margin_room=min(1, max(0, float(row["margin_room"] or 0))),
                historical_lift=min(1, growth / 5),
                available_quantity=available,
                product_views=views,
                completed_transactions=completed,
                abandoned_carts=abandoned,
                demand_sessions=sessions,
                accepted_growth_events=growth,
            )
            score, reasons = OpportunityScore.calculate(metrics, weights)
            if score < 0.20:
                continue
            if db.execute(
                text(
                    """select 1 from campaign_opportunities where merchant_id=:merchant
                    and status='OPEN' and expires_at>now() and product_ids ? :product"""
                ),
                {"merchant": merchant_id, "product": str(row["product_id"])},
            ).scalar():
                continue
            record = (
                db.execute(
                    text(
                        """insert into campaign_opportunities(merchant_id,trigger_type,product_ids,recommended_campaign_type,score,reasons,input_metrics,expires_at)
                        values(:merchant,:trigger,cast(:products as jsonb),'INVENTORY_CONVERSION',:score,cast(:reasons as jsonb),cast(:metrics as jsonb),:expires) returning *"""
                    ),
                    {
                        "merchant": merchant_id,
                        "trigger": trigger_type,
                        "products": json.dumps([str(row["product_id"])]),
                        "score": score,
                        "reasons": json.dumps(reasons),
                        "metrics": metrics.model_dump_json(),
                        "expires": datetime.now(UTC) + timedelta(hours=24),
                    },
                )
                .mappings()
                .one()
            )
            created.append(dict(record))
        db.commit()
        return created


class CampaignEligibilityService:
    @staticmethod
    def evaluate(campaign: dict, mandate: dict, cart: dict, product_ids: set[str]) -> dict:
        cart_products = {str(item["product_id"]) for item in cart["items"]}
        rules = campaign.get("eligibility") or {}
        remaining_budget = int(mandate["max_total_amount_minor"]) - int(cart["total_minor"])
        product_match = bool(cart_products & product_ids)
        segment_match = (
            remaining_budget >= int(rules.get("minimum_remaining_budget_minor", 0))
            and int(cart["total_minor"]) >= int(rules.get("minimum_cart_total_minor", 0))
        )
        return {
            "product_eligible": product_match,
            "segment_eligible": segment_match,
            "remaining_budget_minor": remaining_budget,
            "rules": rules,
            "eligible": product_match and segment_match and bool(mandate["campaign_offer_allowed"]),
        }


class CampaignService:
    @staticmethod
    def discount_minor(campaign: dict, eligible_subtotal_minor: int) -> int:
        raw = (
            eligible_subtotal_minor * int(campaign["discount_value"]) // 10_000
            if campaign["discount_type"] == "PERCENT"
            else int(campaign["discount_value"])
        )
        return min(raw, int(campaign["max_discount_per_order_minor"]))

    @staticmethod
    def stop_reason(campaign: dict, inventory_available: int, now: datetime | None = None):
        at = now or datetime.now(UTC)
        if at >= campaign["end_time"]:
            return "END_TIME_REACHED"
        if int(campaign["used_discount_budget_minor"]) + int(
            campaign.get("reserved_discount_budget_minor", 0)
        ) >= int(
            campaign["total_discount_budget_minor"]
        ):
            return "BUDGET_EXHAUSTED"
        if int(campaign["current_redemptions"]) + int(
            campaign.get("reserved_redemptions", 0)
        ) >= int(campaign["maximum_redemptions"]):
            return "REDEMPTIONS_EXHAUSTED"
        threshold = int((campaign.get("stop_conditions") or {}).get("inventory_below", -1))
        if threshold >= 0 and inventory_available <= threshold:
            return "INVENTORY_THRESHOLD_CROSSED"
        return None


class CampaignOrchestrator:
    @staticmethod
    def run_cycle(
        db: Session,
        inventory_threshold: int = 15,
        weights: dict[str, float] | None = None,
    ) -> dict:
        db.execute(
            text(
                "update campaign_opportunities set status='EXPIRED' where status='OPEN' and expires_at<=now()"
            )
        )
        scanned = 0
        for merchant_id in db.execute(text("select id from merchants")).scalars():
            scanned += len(
                CampaignOpportunityService.scan(
                    db, merchant_id, "SCHEDULED", inventory_threshold, weights
                )
            )
        activated = db.execute(
            text(
                """update campaigns set status='ACTIVE' where status in ('APPROVED','SCHEDULED')
                and start_time<=now() and end_time>now() returning id,merchant_id"""
            )
        ).mappings().all()
        for row in activated:
            db.execute(
                text(
                    "insert into campaign_events(campaign_id,merchant_id,event_type,actor_type) values(:campaign,:merchant,'CAMPAIGN_ACTIVATED','SCHEDULER')"
                ),
                {"campaign": row["id"], "merchant": row["merchant_id"]},
            )
        stopped = []
        campaigns = db.execute(
            text("select * from campaigns where status='ACTIVE' for update")
        ).mappings()
        for row in campaigns:
            inventory = int(
                db.execute(
                    text(
                        """select coalesce(sum(i.available_quantity-i.reserved_quantity),0)
                        from campaign_products cp join merchant_inventory i on i.product_id=cp.product_id
                        where cp.campaign_id=:campaign"""
                    ),
                    {"campaign": row["id"]},
                ).scalar_one()
            )
            reason = CampaignService.stop_reason(dict(row), inventory)
            if not reason:
                continue
            status = "COMPLETED" if reason in {
                "END_TIME_REACHED",
                "BUDGET_EXHAUSTED",
                "REDEMPTIONS_EXHAUSTED",
            } else "PAUSED"
            db.execute(
                text("update campaigns set status=:status where id=:id"),
                {"status": status, "id": row["id"]},
            )
            db.execute(
                text(
                    """insert into campaign_events(campaign_id,merchant_id,event_type,actor_type,payload)
                    values(:campaign,:merchant,'CAMPAIGN_AUTO_STOPPED','SCHEDULER',cast(:payload as jsonb))"""
                ),
                {
                    "campaign": row["id"],
                    "merchant": row["merchant_id"],
                    "payload": json.dumps({"reason": reason}),
                },
            )
            stopped.append(str(row["id"]))
        db.commit()
        return {"opportunities_created": scanned, "activated": len(activated), "stopped": stopped}
