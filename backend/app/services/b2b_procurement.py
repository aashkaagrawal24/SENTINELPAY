import hashlib
import json
import time
from dataclasses import dataclass
from uuid import UUID

from z3 import Int, Optimize, Sum, sat

from app.schemas.advanced import SealedBidInput, VcgProcurementRequest
from app.services.advanced_privacy import WesolowskiVdfService


@dataclass(frozen=True)
class Allocation:
    bid_id: UUID
    vendor_id: UUID
    quantity: int
    reported_cost_minor: int
    objective_cost_minor: int


class SealedBidService:
    @staticmethod
    def canonical(bid: SealedBidInput) -> str:
        return json.dumps(
            {
                "bid_id": str(bid.bid_id),
                "vendor_id": str(bid.vendor_id),
                "unit_cost_minor": bid.unit_cost_minor,
                "quantity": bid.quantity,
                "delivery_days": bid.delivery_days,
                "risk_basis_points": bid.risk_basis_points,
                "nonce": bid.nonce,
            },
            sort_keys=True,
            separators=(",", ":"),
        )

    @classmethod
    def commit(cls, bid: SealedBidInput) -> str:
        return hashlib.sha256(cls.canonical(bid).encode()).hexdigest()

    @classmethod
    def verify_reveal(cls, bid: SealedBidInput, commitment: str) -> bool:
        return hashlib.sha256(cls.canonical(bid).encode()).hexdigest() == commitment


class VcgProcurementService:
    """Reverse-auction VCG with exact quantity and explicit delivery/risk objective."""

    @staticmethod
    def _eligible(body: VcgProcurementRequest, excluded_vendor: UUID | None = None) -> list[SealedBidInput]:
        approved = set(body.approved_vendor_ids)
        return [
            bid
            for bid in body.bids
            if bid.vendor_id in approved
            and bid.vendor_id != excluded_vendor
            and bid.delivery_days <= body.delivery_deadline_days
        ]

    @classmethod
    def _allocate(
        cls, body: VcgProcurementRequest, excluded_vendor: UUID | None = None
    ) -> tuple[list[Allocation], int] | None:
        bids = cls._eligible(body, excluded_vendor)
        if not bids or sum(item.quantity for item in bids) < body.required_quantity:
            return None
        optimizer = Optimize()
        quantities = [Int(f"quantity_{index}") for index in range(len(bids))]
        for quantity, bid in zip(quantities, bids, strict=True):
            optimizer.add(quantity >= 0, quantity <= bid.quantity)
        optimizer.add(Sum(quantities) == body.required_quantity)
        objective_terms = []
        for quantity, bid in zip(quantities, bids, strict=True):
            risk_penalty = bid.unit_cost_minor * bid.risk_basis_points // 10_000
            delivery_penalty = bid.delivery_days * 100
            objective_terms.append(quantity * (bid.unit_cost_minor + risk_penalty + delivery_penalty))
        objective = Sum(objective_terms)
        optimizer.minimize(objective)
        if optimizer.check() != sat:
            return None
        model = optimizer.model()
        allocations = []
        for quantity, bid in zip(quantities, bids, strict=True):
            allocated = model.eval(quantity).as_long()
            if allocated:
                reported = allocated * bid.unit_cost_minor
                objective_cost = allocated * (
                    bid.unit_cost_minor
                    + bid.unit_cost_minor * bid.risk_basis_points // 10_000
                    + bid.delivery_days * 100
                )
                allocations.append(
                    Allocation(bid.bid_id, bid.vendor_id, allocated, reported, objective_cost)
                )
        return allocations, model.eval(objective).as_long()

    @classmethod
    def execute(cls, body: VcgProcurementRequest) -> dict:
        started = time.perf_counter()
        commitments = {str(bid.bid_id): SealedBidService.commit(bid) for bid in body.bids}
        aggregate_commitment = hashlib.sha256(
            "|".join(commitments[key] for key in sorted(commitments)).encode()
        ).hexdigest()
        vdf = WesolowskiVdfService.evaluate(aggregate_commitment, body.vdf_iterations)
        reveals_valid = all(
            SealedBidService.verify_reveal(bid, commitments[str(bid.bid_id)]) for bid in body.bids
        )
        if not vdf["verified"] or not reveals_valid:
            return {
                "status": "DENIED",
                "reason": "SEALED_BID_REVEAL_VERIFICATION_FAILED",
                "vdf": vdf,
                "payment_created": False,
            }
        optimal = cls._allocate(body)
        if optimal is None:
            return {
                "status": "NO_FEASIBLE_ALLOCATION",
                "reason": "QUANTITY_DELIVERY_OR_VENDOR_CONSTRAINT",
                "vdf": vdf,
                "payment_created": False,
            }
        allocations, optimal_objective = optimal
        reported_total = sum(item.reported_cost_minor for item in allocations)
        if reported_total > body.max_budget_minor:
            return {
                "status": "NO_FEASIBLE_ALLOCATION",
                "reason": "REPORTED_COST_EXCEEDS_BUYER_BUDGET",
                "vdf": vdf,
                "payment_created": False,
            }
        vendor_costs: dict[UUID, int] = {}
        vendor_objectives: dict[UUID, int] = {}
        for allocation in allocations:
            vendor_costs[allocation.vendor_id] = vendor_costs.get(allocation.vendor_id, 0) + allocation.reported_cost_minor
            vendor_objectives[allocation.vendor_id] = vendor_objectives.get(allocation.vendor_id, 0) + allocation.objective_cost_minor
        payments = []
        for vendor_id, reported_cost in vendor_costs.items():
            alternative = cls._allocate(body, excluded_vendor=vendor_id)
            if alternative is None:
                payment = body.buyer_value_per_unit_minor * sum(
                    item.quantity for item in allocations if item.vendor_id == vendor_id
                )
                externality = payment - reported_cost
                pivotal = True
            else:
                _, alternative_objective = alternative
                others_objective = optimal_objective - vendor_objectives[vendor_id]
                payment = max(reported_cost, alternative_objective - others_objective)
                externality = payment - reported_cost
                pivotal = False
            payments.append(
                {
                    "vendor_id": str(vendor_id),
                    "reported_cost_minor": reported_cost,
                    "vcg_payment_minor": payment,
                    "information_rent_minor": externality,
                    "pivotal_without_feasible_alternative": pivotal,
                }
            )
        vcg_total = sum(item["vcg_payment_minor"] for item in payments)
        settlement_allowed = vcg_total <= body.max_budget_minor
        return {
            "status": "ALLOCATED" if settlement_allowed else "REQUIRES_BUYER_APPROVAL",
            "mechanism": "VCG_REVERSE_PROCUREMENT",
            "allocation": [
                {
                    "bid_id": str(item.bid_id),
                    "vendor_id": str(item.vendor_id),
                    "quantity": item.quantity,
                    "reported_cost_minor": item.reported_cost_minor,
                    "objective_cost_minor": item.objective_cost_minor,
                }
                for item in allocations
            ],
            "winner_payments": payments,
            "reported_total_minor": reported_total,
            "vcg_total_minor": vcg_total,
            "max_budget_minor": body.max_budget_minor,
            "social_welfare_minor": body.buyer_value_per_unit_minor * body.required_quantity - optimal_objective,
            "objective": "MAXIMIZE_BUYER_VALUE_MINUS_COST_DELIVERY_AND_RISK",
            "constraints": [
                "TOTAL_COST_WITHIN_BUDGET",
                "EXACT_REQUIRED_QUANTITY",
                "DELIVERY_WITHIN_DEADLINE",
                "APPROVED_VENDOR_ONLY",
                "BID_QUANTITY_LIMIT",
            ],
            "commitments": commitments,
            "reveals_valid": reveals_valid,
            "vdf": vdf,
            "settlement": {
                "mode": "CONTROLLED_MULTI_PAYMENT_SIMULATION",
                "status": "READY" if settlement_allowed else "BLOCKED_BUDGET",
                "entries": payments if settlement_allowed else [],
                "razorpay_orders_created": 0,
            },
            "security_kernel_still_required": True,
            "payment_created": False,
            "elapsed_ms": int((time.perf_counter() - started) * 1000),
        }
