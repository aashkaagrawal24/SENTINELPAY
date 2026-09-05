import hashlib
import json
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas.advanced import VcgProcurementRequest


class B2bProcurementRepository:
    """Persists the complete controlled RFQ, sealed-bid, VDF and VCG trace."""

    @staticmethod
    def _assert_vendors_exist(db: Session, vendor_ids: list[UUID]) -> None:
        placeholders = ",".join(f":vendor_{index}" for index in range(len(vendor_ids)))
        params = {f"vendor_{index}": vendor_id for index, vendor_id in enumerate(vendor_ids)}
        found = db.execute(
            text(f"select count(*) from merchants where id in ({placeholders})"), params
        ).scalar_one()
        if found != len(vendor_ids):
            raise ValueError("all approved vendors must be existing SentinelPay merchants")

    def persist(
        self,
        db: Session,
        *,
        user_id: UUID,
        request: VcgProcurementRequest,
        result: dict,
    ) -> dict[str, UUID]:
        self._assert_vendors_exist(db, request.approved_vendor_ids)
        rfq_status = "OPTIMIZED" if result["status"] == "ALLOCATED" else "OPEN"
        rfq_id = db.execute(
            text(
                """insert into procurement_rfqs(
                user_id,product_query,required_quantity,max_budget_minor,currency,
                approved_vendor_ids,delivery_deadline,status
                ) values(
                :user,'CONTROLLED_MULTI_VENDOR_PROCUREMENT',:quantity,:budget,'INR',
                cast(:vendors as jsonb),now()+make_interval(days => :deadline),:status
                ) returning id"""
            ),
            {
                "user": user_id,
                "quantity": request.required_quantity,
                "budget": request.max_budget_minor,
                "vendors": json.dumps([str(item) for item in request.approved_vendor_ids]),
                "deadline": request.delivery_deadline_days,
                "status": rfq_status,
            },
        ).scalar_one()

        quote_ids: dict[str, UUID] = {}
        for bid in request.bids:
            quote_id = db.execute(
                text(
                    """insert into supplier_quotes(
                    rfq_id,merchant_id,unit_price_minor,available_quantity,delivery_at,
                    vendor_risk_basis_points
                    ) values(
                    :rfq,:vendor,:price,:quantity,now()+make_interval(days => :delivery),:risk
                    ) returning id"""
                ),
                {
                    "rfq": rfq_id,
                    "vendor": bid.vendor_id,
                    "price": bid.unit_cost_minor,
                    "quantity": bid.quantity,
                    "delivery": bid.delivery_days,
                    "risk": bid.risk_basis_points,
                },
            ).scalar_one()
            quote_ids[str(bid.bid_id)] = quote_id
            db.execute(
                text(
                    """insert into sealed_bid_commits(
                    rfq_id,vendor_id,commitment,status,revealed_quote_id,revealed_at
                    ) values(:rfq,:vendor,:commitment,'REVEALED',:quote,now())"""
                ),
                {
                    "rfq": rfq_id,
                    "vendor": bid.vendor_id,
                    "commitment": result["commitments"][str(bid.bid_id)],
                    "quote": quote_id,
                },
            )

        vdf = result["vdf"]
        aggregate_commitment = hashlib.sha256(
            "|".join(result["commitments"][key] for key in sorted(result["commitments"])).encode()
        ).hexdigest()
        vdf_id = db.execute(
            text(
                """insert into vdf_runs(
                purpose,challenge_hash,iterations,output,proof,verified,evaluation_ms
                ) values(:purpose,:challenge,:iterations,:output,:proof,:verified,:elapsed)
                returning id"""
            ),
            {
                "purpose": vdf["purpose"],
                "challenge": hashlib.sha256(aggregate_commitment.encode()).hexdigest(),
                "iterations": vdf["iterations"],
                "output": vdf["y"],
                "proof": vdf["proof"],
                "verified": vdf["verified"],
                "elapsed": vdf["evaluation_ms"],
            },
        ).scalar_one()

        for allocation in result.get("allocation", []):
            db.execute(
                text(
                    """insert into procurement_allocations(
                    rfq_id,quote_id,allocated_quantity,allocated_cost_minor,objective_contribution
                    ) values(:rfq,:quote,:quantity,:cost,:objective)"""
                ),
                {
                    "rfq": rfq_id,
                    "quote": quote_ids[allocation["bid_id"]],
                    "quantity": allocation["quantity"],
                    "cost": allocation["reported_cost_minor"],
                    "objective": allocation["objective_cost_minor"],
                },
            )

        status = {
            "ALLOCATED": "ALLOCATED",
            "REQUIRES_BUYER_APPROVAL": "REQUIRES_APPROVAL",
        }.get(result["status"], "DENIED")
        vcg_id = db.execute(
            text(
                """insert into vcg_results(
                rfq_id,social_welfare_minor,reported_total_minor,vcg_total_minor,
                allocation,winner_payments,vdf_run_id,status
                ) values(:rfq,:welfare,:reported,:vcg,cast(:allocation as jsonb),
                cast(:payments as jsonb),:vdf,:status) returning id"""
            ),
            {
                "rfq": rfq_id,
                "welfare": result.get("social_welfare_minor", 0),
                "reported": result.get("reported_total_minor", 0),
                "vcg": result.get("vcg_total_minor", 0),
                "allocation": json.dumps(result.get("allocation", [])),
                "payments": json.dumps(result.get("winner_payments", [])),
                "vdf": vdf_id,
                "status": status,
            },
        ).scalar_one()
        settlement = result.get("settlement", {})
        settlement_id = db.execute(
            text(
                """insert into procurement_settlement_simulations(
                vcg_result_id,status,entries,total_minor,razorpay_orders_created
                ) values(:vcg,:status,cast(:entries as jsonb),:total,0) returning id"""
            ),
            {
                "vcg": vcg_id,
                "status": "READY" if settlement.get("status") == "READY" else "BLOCKED",
                "entries": json.dumps(settlement.get("entries", [])),
                "total": result.get("vcg_total_minor", 0),
            },
        ).scalar_one()
        db.commit()
        return {
            "rfq_id": rfq_id,
            "vdf_run_id": vdf_id,
            "vcg_result_id": vcg_id,
            "settlement_simulation_id": settlement_id,
        }
