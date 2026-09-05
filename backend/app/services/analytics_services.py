import hashlib
import json
from datetime import datetime
from uuid import UUID, uuid5

from sqlalchemy import text
from sqlalchemy.orm import Session


def safe_rate(numerator: float, denominator: float) -> float:
    return float(numerator) / float(denominator) if denominator else 0.0


class CampaignAssignmentService:
    @staticmethod
    def bucket(mandate_id: UUID, campaign_id: UUID) -> int:
        digest = hashlib.sha256(f"{mandate_id}:{campaign_id}".encode()).digest()
        return int.from_bytes(digest[:8], "big") % 100

    @staticmethod
    def group(bucket: int, control_percentage: int, experiment_enabled: bool) -> str:
        return (
            "CONTROL"
            if experiment_enabled and bucket < control_percentage
            else "TREATMENT"
        )

    @classmethod
    def assign(
        cls,
        db: Session,
        campaign_id: UUID,
        mandate_id: UUID,
        control_percentage: int,
        experiment_enabled: bool,
    ) -> dict:
        bucket = cls.bucket(mandate_id, campaign_id)
        group = cls.group(bucket, control_percentage, experiment_enabled)
        row = (
            db.execute(
                text(
                    """insert into campaign_assignments(campaign_id,mandate_id,agent_session_id,bucket_value,assignment_group)
                    values(:campaign,:mandate,(select id from agent_sessions where mandate_id=:mandate order by started_at desc limit 1),:bucket,:group)
                    on conflict(campaign_id,mandate_id) do update set campaign_id=excluded.campaign_id
                    returning *"""
                ),
                {
                    "campaign": campaign_id,
                    "mandate": mandate_id,
                    "bucket": bucket,
                    "group": group,
                },
            )
            .mappings()
            .one()
        )
        return dict(row)


class AttributionCalculator:
    @staticmethod
    def campaign(values: dict) -> dict:
        control_sessions = int(values.get("control_sessions", 0))
        treatment_sessions = int(values.get("treatment_sessions", 0))
        control_conversions = int(values.get("control_conversions", 0))
        treatment_conversions = int(values.get("treatment_conversions", 0))
        control_revenue = int(values.get("control_revenue_minor", 0))
        treatment_revenue = int(values.get("treatment_revenue_minor", 0))
        discount = int(values.get("discount_cost_minor", 0))
        control_cr = safe_rate(control_conversions, control_sessions)
        treatment_cr = safe_rate(treatment_conversions, treatment_sessions)
        control_aov = round(safe_rate(control_revenue, control_conversions))
        treatment_aov = round(safe_rate(treatment_revenue, treatment_conversions))
        has_control = control_sessions > 0 and treatment_sessions > 0
        incremental = (
            round(
                (
                    safe_rate(treatment_revenue, treatment_sessions)
                    - safe_rate(control_revenue, control_sessions)
                )
                * treatment_sessions
            )
            if has_control
            else None
        )
        basis = incremental if incremental is not None else int(
            values.get("attributed_revenue_minor", 0)
        )
        return {
            **values,
            "eligible_sessions": control_sessions + treatment_sessions,
            "control_conversion_rate": control_cr,
            "treatment_conversion_rate": treatment_cr,
            "conversion_rate_lift": treatment_cr - control_cr if has_control else None,
            "control_aov_minor": control_aov,
            "treatment_aov_minor": treatment_aov,
            "aov_lift_minor": treatment_aov - control_aov if has_control else None,
            "incremental_revenue_estimate_minor": incremental,
            "revenue_per_discount_rupee": safe_rate(basis, discount),
            "attribution_label": (
                "CONTROLLED EXPERIMENT ESTIMATE"
                if has_control
                else "ATTRIBUTED CAMPAIGN REVENUE"
            ),
        }


class RevenueAnalyticsService:
    @staticmethod
    def counts_as_real_revenue(
        transaction_status: str, payment_status: str, data_scope: str = "REAL"
    ) -> bool:
        return (
            data_scope == "REAL"
            and transaction_status == "SUCCESS"
            and payment_status == "CAPTURED"
        )

    @staticmethod
    def _campaign_real(db: Session, campaign_id: UUID, start: datetime, end: datetime) -> dict:
        row = db.execute(
            text(
                """select
                count(*) filter(where ca.assignment_group='CONTROL') control_sessions,
                count(*) filter(where ca.assignment_group='TREATMENT') treatment_sessions,
                count(*) filter(where ca.assignment_group='CONTROL' and ca.converted) control_conversions,
                count(*) filter(where ca.assignment_group='TREATMENT' and ca.converted) treatment_conversions,
                coalesce(sum(c.total_minor) filter(where ca.assignment_group='CONTROL' and pa.status='CAPTURED' and t.status='SUCCESS'),0) control_revenue_minor,
                coalesce(sum(c.total_minor) filter(where ca.assignment_group='TREATMENT' and pa.status='CAPTURED' and t.status='SUCCESS'),0) treatment_revenue_minor
                from campaign_assignments ca left join transactions t on t.id=ca.transaction_id and t.data_scope='REAL'
                left join payment_attempts pa on pa.transaction_id=t.id left join carts c on c.id=t.cart_id
                where ca.campaign_id=:campaign and ca.data_scope='REAL' and ca.assigned_at>=:start and ca.assigned_at<:end"""
            ),
            {"campaign": campaign_id, "start": start, "end": end},
        ).mappings().one()
        extras = db.execute(
            text(
                """select
                (select count(*) from campaign_offers where campaign_id=:campaign and created_at>=:start and created_at<:end) offers_served,
                coalesce((select sum(c.total_minor) from campaign_redemptions cr join transactions t on t.id=cr.transaction_id
                  join payment_attempts pa on pa.transaction_id=t.id join carts c on c.id=t.cart_id
                  where cr.campaign_id=:campaign and cr.status='REDEEMED' and t.status='SUCCESS' and pa.status='CAPTURED'
                  and cr.created_at>=:start and cr.created_at<:end),0) attributed_revenue_minor,
                coalesce((select sum(discount_minor) from campaign_redemptions where campaign_id=:campaign and status='REDEEMED'
                  and created_at>=:start and created_at<:end),0) discount_cost_minor,
                coalesce((select sum(ue.incremental_revenue_minor) from upsell_events ue join transactions t on t.id=ue.transaction_id
                  join payment_attempts pa on pa.transaction_id=t.id join campaign_assignments ca on ca.transaction_id=t.id
                  where ca.campaign_id=:campaign and ue.accepted and t.status='SUCCESS' and pa.status='CAPTURED'
                  and ue.created_at>=:start and ue.created_at<:end),0) upsell_revenue_minor,
                coalesce((select sum(ce.incremental_revenue_minor) from cross_sell_events ce join transactions t on t.id=ce.transaction_id
                  join payment_attempts pa on pa.transaction_id=t.id join campaign_assignments ca on ca.transaction_id=t.id
                  where ca.campaign_id=:campaign and ce.accepted and t.status='SUCCESS' and pa.status='CAPTURED'
                  and ce.created_at>=:start and ce.created_at<:end),0) cross_sell_revenue_minor"""
            ),
            {"campaign": campaign_id, "start": start, "end": end},
        ).mappings().one()
        values = {**dict(row), **dict(extras)}
        values["gross_revenue_minor"] = int(values["control_revenue_minor"]) + int(
            values["treatment_revenue_minor"]
        )
        return values

    @staticmethod
    def _campaign_simulated(
        db: Session, campaign_id: UUID, start: datetime, end: datetime
    ) -> dict:
        return dict(
            db.execute(
                text(
                    """select count(*) filter(where assignment_group='CONTROL') control_sessions,
                    count(*) filter(where assignment_group='TREATMENT') treatment_sessions,
                    count(*) filter(where assignment_group='CONTROL' and converted) control_conversions,
                    count(*) filter(where assignment_group='TREATMENT' and converted) treatment_conversions,
                    coalesce(sum(gross_revenue_minor) filter(where assignment_group='CONTROL' and converted),0) control_revenue_minor,
                    coalesce(sum(gross_revenue_minor) filter(where assignment_group='TREATMENT' and converted),0) treatment_revenue_minor,
                    count(*) filter(where assignment_group='TREATMENT') offers_served,
                    coalesce(sum(attributed_revenue_minor),0) attributed_revenue_minor,
                    coalesce(sum(discount_cost_minor),0) discount_cost_minor,
                    coalesce(sum(upsell_revenue_minor),0) upsell_revenue_minor,
                    coalesce(sum(cross_sell_revenue_minor),0) cross_sell_revenue_minor,
                    coalesce(sum(gross_revenue_minor),0) gross_revenue_minor
                    from simulated_commerce_sessions where campaign_id=:campaign and created_at>=:start and created_at<:end"""
                ),
                {"campaign": campaign_id, "start": start, "end": end},
            ).mappings().one()
        )

    @classmethod
    def refresh_campaign(
        cls,
        db: Session,
        campaign_id: UUID,
        start: datetime,
        end: datetime,
        scope: str,
    ) -> dict:
        raw = (
            cls._campaign_real(db, campaign_id, start, end)
            if scope == "REAL"
            else cls._campaign_simulated(db, campaign_id, start, end)
        )
        metric = AttributionCalculator.campaign(raw)
        row = (
            db.execute(
                text(
                    """insert into campaign_metrics(campaign_id,window_start,window_end,data_scope,eligible_sessions,
                    control_sessions,treatment_sessions,offers_served,control_conversions,treatment_conversions,gross_revenue_minor,
                    attributed_revenue_minor,discount_cost_minor,control_revenue_minor,treatment_revenue_minor,incremental_revenue_estimate_minor,
                    upsell_revenue_minor,cross_sell_revenue_minor,control_conversion_rate,treatment_conversion_rate,conversion_rate_lift,
                    control_aov_minor,treatment_aov_minor,aov_lift_minor,revenue_per_discount_rupee,attribution_label)
                    values(:campaign,:start,:end,:scope,:eligible_sessions,:control_sessions,:treatment_sessions,:offers_served,
                    :control_conversions,:treatment_conversions,:gross_revenue_minor,:attributed_revenue_minor,:discount_cost_minor,
                    :control_revenue_minor,:treatment_revenue_minor,:incremental_revenue_estimate_minor,:upsell_revenue_minor,
                    :cross_sell_revenue_minor,:control_conversion_rate,:treatment_conversion_rate,:conversion_rate_lift,
                    :control_aov_minor,:treatment_aov_minor,:aov_lift_minor,:revenue_per_discount_rupee,:attribution_label)
                    on conflict(campaign_id,window_start,window_end,data_scope) do update set
                    eligible_sessions=excluded.eligible_sessions,control_sessions=excluded.control_sessions,treatment_sessions=excluded.treatment_sessions,
                    offers_served=excluded.offers_served,control_conversions=excluded.control_conversions,treatment_conversions=excluded.treatment_conversions,
                    gross_revenue_minor=excluded.gross_revenue_minor,attributed_revenue_minor=excluded.attributed_revenue_minor,
                    discount_cost_minor=excluded.discount_cost_minor,control_revenue_minor=excluded.control_revenue_minor,
                    treatment_revenue_minor=excluded.treatment_revenue_minor,incremental_revenue_estimate_minor=excluded.incremental_revenue_estimate_minor,
                    upsell_revenue_minor=excluded.upsell_revenue_minor,cross_sell_revenue_minor=excluded.cross_sell_revenue_minor,
                    control_conversion_rate=excluded.control_conversion_rate,treatment_conversion_rate=excluded.treatment_conversion_rate,
                    conversion_rate_lift=excluded.conversion_rate_lift,control_aov_minor=excluded.control_aov_minor,
                    treatment_aov_minor=excluded.treatment_aov_minor,aov_lift_minor=excluded.aov_lift_minor,
                    revenue_per_discount_rupee=excluded.revenue_per_discount_rupee,attribution_label=excluded.attribution_label,updated_at=now()
                    returning *"""
                ),
                {
                    "campaign": campaign_id,
                    "start": start,
                    "end": end,
                    "scope": scope,
                    **metric,
                },
            )
            .mappings()
            .one()
        )
        return dict(row)

    @classmethod
    def refresh_merchant(
        cls, db: Session, merchant_id: UUID, start: datetime, end: datetime, scope: str
    ) -> dict:
        if scope == "SIMULATED":
            raw = dict(
                db.execute(
                    text(
                        """select count(*) ai_sessions,count(*) agent_carts,count(*) filter(where converted) successful_orders,
                        count(*) filter(where converted) checkout_attempts,coalesce(sum(gross_revenue_minor),0) gross_ai_revenue_minor,
                        0 negotiation_sessions,0 negotiation_conversions,0 negotiation_revenue_minor,0 negotiation_discount_cost_minor,
                        count(*) upsell_offers,count(*) filter(where upsell_revenue_minor>0) upsell_acceptances,
                        coalesce(sum(upsell_revenue_minor),0) upsell_revenue_minor,count(*) cross_sell_offers,
                        count(*) filter(where cross_sell_revenue_minor>0) cross_sell_acceptances,
                        coalesce(sum(cross_sell_revenue_minor),0) cross_sell_revenue_minor,
                        count(*) filter(where assignment_group='TREATMENT') campaign_offers,
                        count(*) filter(where assignment_group='TREATMENT' and converted) campaign_conversions,
                        coalesce(sum(attributed_revenue_minor),0) campaign_attributed_revenue_minor,
                        coalesce(sum(discount_cost_minor),0) campaign_discount_cost_minor,0 policy_violations_blocked
                        from simulated_commerce_sessions where merchant_id=:merchant and created_at>=:start and created_at<:end"""
                    ),
                    {"merchant": merchant_id, "start": start, "end": end},
                ).mappings().one()
            )
        else:
            raw = dict(
                db.execute(
                    text(
                        """select
                        (select count(*) from agent_sessions where merchant_id=:merchant and started_at>=:start and started_at<:end and coalesce(metadata->>'provenance','REAL')<>'SIMULATED') ai_sessions,
                        (select count(*) from carts where merchant_id=:merchant and created_at>=:start and created_at<:end) agent_carts,
                        (select count(*) from transactions t join carts c on c.id=t.cart_id where c.merchant_id=:merchant and t.data_scope='REAL' and t.created_at>=:start and t.created_at<:end) checkout_attempts,
                        (select count(distinct t.id) from transactions t join carts c on c.id=t.cart_id join payment_attempts pa on pa.transaction_id=t.id where c.merchant_id=:merchant and t.data_scope='REAL' and t.status='SUCCESS' and pa.status='CAPTURED' and t.created_at>=:start and t.created_at<:end) successful_orders,
                        coalesce((select sum(c.total_minor) from transactions t join carts c on c.id=t.cart_id join payment_attempts pa on pa.transaction_id=t.id where c.merchant_id=:merchant and t.data_scope='REAL' and t.status='SUCCESS' and pa.status='CAPTURED' and t.created_at>=:start and t.created_at<:end),0) gross_ai_revenue_minor,
                        (select count(*) from negotiation_sessions where merchant_id=:merchant and created_at>=:start and created_at<:end) negotiation_sessions,
                        (select count(distinct t.id) from negotiation_sessions ns join transactions t on t.cart_id=ns.fallback_cart_id join payment_attempts pa on pa.transaction_id=t.id where ns.merchant_id=:merchant and t.status='SUCCESS' and pa.status='CAPTURED' and t.created_at>=:start and t.created_at<:end) negotiation_conversions,
                        coalesce((select sum(c.total_minor) from negotiation_sessions ns join transactions t on t.cart_id=ns.fallback_cart_id join carts c on c.id=t.cart_id join payment_attempts pa on pa.transaction_id=t.id where ns.merchant_id=:merchant and t.status='SUCCESS' and pa.status='CAPTURED' and t.created_at>=:start and t.created_at<:end),0) negotiation_revenue_minor,
                        coalesce((select sum(starting_price_minor-final_agreed_price_minor) from negotiation_sessions where merchant_id=:merchant and status in ('ACCEPTED','FALLBACK') and created_at>=:start and created_at<:end),0) negotiation_discount_cost_minor,
                        (select count(*) from upsell_events where merchant_id=:merchant and created_at>=:start and created_at<:end) upsell_offers,
                        (select count(*) from upsell_events ue join transactions t on t.id=ue.transaction_id join payment_attempts pa on pa.transaction_id=t.id where ue.merchant_id=:merchant and ue.accepted and t.status='SUCCESS' and pa.status='CAPTURED' and ue.created_at>=:start and ue.created_at<:end) upsell_acceptances,
                        coalesce((select sum(incremental_revenue_minor) from upsell_events ue join transactions t on t.id=ue.transaction_id join payment_attempts pa on pa.transaction_id=t.id where ue.merchant_id=:merchant and ue.accepted and t.status='SUCCESS' and pa.status='CAPTURED' and ue.created_at>=:start and ue.created_at<:end),0) upsell_revenue_minor,
                        (select count(*) from cross_sell_events where merchant_id=:merchant and created_at>=:start and created_at<:end) cross_sell_offers,
                        (select count(*) from cross_sell_events ce join transactions t on t.id=ce.transaction_id join payment_attempts pa on pa.transaction_id=t.id where ce.merchant_id=:merchant and ce.accepted and t.status='SUCCESS' and pa.status='CAPTURED' and ce.created_at>=:start and ce.created_at<:end) cross_sell_acceptances,
                        coalesce((select sum(incremental_revenue_minor) from cross_sell_events ce join transactions t on t.id=ce.transaction_id join payment_attempts pa on pa.transaction_id=t.id where ce.merchant_id=:merchant and ce.accepted and t.status='SUCCESS' and pa.status='CAPTURED' and ce.created_at>=:start and ce.created_at<:end),0) cross_sell_revenue_minor,
                        (select count(*) from campaign_offers co join campaigns ca on ca.id=co.campaign_id where ca.merchant_id=:merchant and co.created_at>=:start and co.created_at<:end) campaign_offers,
                        (select count(*) from campaign_redemptions cr join campaigns ca on ca.id=cr.campaign_id where ca.merchant_id=:merchant and cr.status='REDEEMED' and cr.created_at>=:start and cr.created_at<:end) campaign_conversions,
                        coalesce((select sum(c.total_minor) from campaign_redemptions cr join campaigns ca on ca.id=cr.campaign_id join transactions t on t.id=cr.transaction_id join carts c on c.id=t.cart_id join payment_attempts pa on pa.transaction_id=t.id where ca.merchant_id=:merchant and cr.status='REDEEMED' and t.status='SUCCESS' and pa.status='CAPTURED' and cr.created_at>=:start and cr.created_at<:end),0) campaign_attributed_revenue_minor,
                        coalesce((select sum(discount_minor) from campaign_redemptions cr join campaigns ca on ca.id=cr.campaign_id where ca.merchant_id=:merchant and cr.status='REDEEMED' and cr.created_at>=:start and cr.created_at<:end),0) campaign_discount_cost_minor,
                        (select count(*) from transactions t join carts c on c.id=t.cart_id where c.merchant_id=:merchant and t.data_scope='REAL' and t.status='DENIED' and t.created_at>=:start and t.created_at<:end) policy_violations_blocked"""
                    ),
                    {"merchant": merchant_id, "start": start, "end": end},
                ).mappings().one()
            )
        successful = int(raw["successful_orders"])
        processed_refunds_minor = 0
        if scope == "REAL":
            processed_refunds_minor = int(
                db.execute(
                    text(
                        """select coalesce(sum(r.amount_minor),0) from refunds r
                        join payment_attempts pa on pa.id=r.payment_attempt_id
                        join transactions t on t.id=pa.transaction_id join carts c on c.id=t.cart_id
                        where c.merchant_id=:merchant and r.status='PROCESSED'
                        and r.updated_at>=:start and r.updated_at<:end"""
                    ),
                    {"merchant": merchant_id, "start": start, "end": end},
                ).scalar_one()
            )
        raw["processed_refunds_minor"] = processed_refunds_minor
        raw["net_revenue_minor"] = int(raw["gross_ai_revenue_minor"]) - processed_refunds_minor
        raw["conversion_rate"] = safe_rate(successful, int(raw["ai_sessions"]))
        raw["average_order_value_minor"] = round(
            safe_rate(int(raw["gross_ai_revenue_minor"]), successful)
        )
        campaign_estimate = db.execute(
            text(
                """select sum(cm.incremental_revenue_estimate_minor) from campaign_metrics cm join campaigns c on c.id=cm.campaign_id
                where c.merchant_id=:merchant and cm.data_scope=:scope and cm.window_start=:start and cm.window_end=:end"""
            ),
            {"merchant": merchant_id, "scope": scope, "start": start, "end": end},
        ).scalar()
        raw["controlled_incremental_estimate_minor"] = campaign_estimate
        row = (
            db.execute(
                text(
                    """insert into merchant_metrics(merchant_id,period_start,period_end,data_scope,ai_sessions,agent_carts,checkout_attempts,
                    successful_orders,gross_ai_revenue_minor,conversion_rate,average_order_value_minor,negotiation_sessions,negotiation_conversions,
                    negotiation_revenue_minor,negotiation_discount_cost_minor,upsell_offers,upsell_acceptances,upsell_revenue_minor,
                    cross_sell_offers,cross_sell_acceptances,cross_sell_revenue_minor,campaign_offers,campaign_conversions,
                    campaign_attributed_revenue_minor,controlled_incremental_estimate_minor,campaign_discount_cost_minor,policy_violations_blocked)
                    values(:merchant,:start,:end,:scope,:ai_sessions,:agent_carts,:checkout_attempts,:successful_orders,:gross_ai_revenue_minor,
                    :conversion_rate,:average_order_value_minor,:negotiation_sessions,:negotiation_conversions,:negotiation_revenue_minor,
                    :negotiation_discount_cost_minor,:upsell_offers,:upsell_acceptances,:upsell_revenue_minor,:cross_sell_offers,
                    :cross_sell_acceptances,:cross_sell_revenue_minor,:campaign_offers,:campaign_conversions,:campaign_attributed_revenue_minor,
                    :controlled_incremental_estimate_minor,:campaign_discount_cost_minor,:policy_violations_blocked)
                    on conflict(merchant_id,period_start,period_end,data_scope) do update set
                    ai_sessions=excluded.ai_sessions,agent_carts=excluded.agent_carts,checkout_attempts=excluded.checkout_attempts,
                    successful_orders=excluded.successful_orders,gross_ai_revenue_minor=excluded.gross_ai_revenue_minor,
                    conversion_rate=excluded.conversion_rate,average_order_value_minor=excluded.average_order_value_minor,
                    negotiation_sessions=excluded.negotiation_sessions,negotiation_conversions=excluded.negotiation_conversions,
                    negotiation_revenue_minor=excluded.negotiation_revenue_minor,negotiation_discount_cost_minor=excluded.negotiation_discount_cost_minor,
                    upsell_offers=excluded.upsell_offers,upsell_acceptances=excluded.upsell_acceptances,upsell_revenue_minor=excluded.upsell_revenue_minor,
                    cross_sell_offers=excluded.cross_sell_offers,cross_sell_acceptances=excluded.cross_sell_acceptances,
                    cross_sell_revenue_minor=excluded.cross_sell_revenue_minor,campaign_offers=excluded.campaign_offers,
                    campaign_conversions=excluded.campaign_conversions,campaign_attributed_revenue_minor=excluded.campaign_attributed_revenue_minor,
                    controlled_incremental_estimate_minor=excluded.controlled_incremental_estimate_minor,
                    campaign_discount_cost_minor=excluded.campaign_discount_cost_minor,policy_violations_blocked=excluded.policy_violations_blocked,updated_at=now()
                    returning *"""
                ),
                {"merchant": merchant_id, "start": start, "end": end, "scope": scope, **raw},
            )
            .mappings()
            .one()
        )
        db.execute(
            text(
                """update merchant_metrics set processed_refunds_minor=:refunds,net_revenue_minor=:net
                where id=:id"""
            ),
            {
                "refunds": processed_refunds_minor,
                "net": raw["net_revenue_minor"],
                "id": row["id"],
            },
        )
        db.commit()
        return dict(row) | {
            "processed_refunds_minor": processed_refunds_minor,
            "net_revenue_minor": raw["net_revenue_minor"],
        }


class SyntheticEvaluationService:
    NAMESPACE = UUID("778632eb-2155-4f2e-9fa7-44941a9fb1cb")

    @classmethod
    def session_id(
        cls, merchant_id: UUID, campaign_id: UUID, seed: int, index: int
    ) -> UUID:
        return uuid5(cls.NAMESPACE, f"{merchant_id}:{campaign_id}:{seed}:{index}")

    @staticmethod
    def generate(
        db: Session,
        merchant_id: UUID,
        campaign_id: UUID,
        count: int,
        seed: int,
        control_percentage: int,
    ) -> int:
        for index in range(count):
            session_id = SyntheticEvaluationService.session_id(
                merchant_id, campaign_id, seed, index
            )
            bucket = int.from_bytes(hashlib.sha256(session_id.bytes).digest()[:8], "big") % 100
            group = "CONTROL" if bucket < control_percentage else "TREATMENT"
            draw = int.from_bytes(hashlib.sha256(f"convert:{session_id}".encode()).digest()[:4], "big") % 100
            converted = draw < (18 if group == "CONTROL" else 28)
            revenue = (1_800_000 + (bucket * 5_000)) if converted else 0
            discount = 0 if group == "CONTROL" or not converted else min(100_000, revenue // 20)
            attributed = revenue if group == "TREATMENT" and converted else 0
            upsell = 49_900 if converted and bucket % 5 == 0 else 0
            cross_sell = 29_900 if converted and bucket % 4 == 0 else 0
            db.execute(
                text(
                    """insert into simulated_commerce_sessions(id,merchant_id,campaign_id,bucket_value,assignment_group,converted,
                    gross_revenue_minor,attributed_revenue_minor,discount_cost_minor,upsell_revenue_minor,cross_sell_revenue_minor,
                    generator_seed,metadata) values(:id,:merchant,:campaign,:bucket,:group,:converted,:revenue,:attributed,
                    :discount,:upsell,:cross_sell,:seed,cast(:metadata as jsonb)) on conflict(id) do nothing"""
                ),
                {
                    "id": session_id,
                    "merchant": merchant_id,
                    "campaign": campaign_id,
                    "bucket": bucket,
                    "group": group,
                    "converted": converted,
                    "revenue": revenue,
                    "attributed": attributed,
                    "discount": discount,
                    "upsell": upsell,
                    "cross_sell": cross_sell,
                    "seed": seed,
                    "metadata": json.dumps(
                        {
                            "provenance": "SIMULATED",
                            "generator": "phase8-deterministic-v1",
                            "conversion_rates": {"CONTROL": 0.18, "TREATMENT": 0.28},
                        }
                    ),
                },
            )
        db.commit()
        return count
