"""
SentinelPay — Bulk Commerce Service Layer
==========================================
Covers:
  - BulkPricingOptimizer   : AI discount grid optimizer (heuristic, labeled)
  - BulkPolicyEngine       : AI quantity-tiered policy recommender
  - BuyerBulkAgent         : Buyer-side negotiation with private constraints never exposed
  - MerchantBulkAgent      : Merchant-side quoting within approved policy bounds (floor never exposed)
  - InventoryReservationService : Atomic reservation with TTL + oversell prevention
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session


# ─────────────────────────────────────────────────────────────────────────────
# BULK PRICING OPTIMIZER
# ─────────────────────────────────────────────────────────────────────────────

class BulkPricingOptimizer:
    """
    For each bulk RFQ, evaluate candidate discount levels and select the one
    that maximises Expected Economic Value (EEV) subject to merchant constraints.

    EEV = (Acceptance_Probability × Contribution_Margin) + Inventory_Clearance_Benefit
          - Risk_Penalty

    Acceptance model: deterministic heuristic based on quantity, inventory pressure,
    and discount depth. NOT a trained ML model — labeled HEURISTIC throughout.
    """

    DISCOUNT_CANDIDATES = [0.0, 3.0, 5.0, 8.0, 10.0, 12.0, 15.0, 16.7, 20.0]

    CATEGORY_COST_RATIO: dict[str, float] = {
        "ice cream": 0.62,
        "dairy": 0.78,
        "grocery": 0.72,
        "beverages": 0.55,
        "electronics": 0.70,
        "headphones": 0.65,
        "audio": 0.65,
    }

    @classmethod
    def _cost_ratio(cls, category: str | None) -> float:
        cat = (category or "").lower()
        for k, v in cls.CATEGORY_COST_RATIO.items():
            if k in cat:
                return v
        return 0.68

    @classmethod
    def _heuristic_acceptance_probability(
        cls,
        discount_pct: float,
        requested_quantity: int,
        available_quantity: int,
        base_price_minor: int,
        private_target_price_minor: int | None,
    ) -> float:
        """
        HEURISTIC (not ML): higher discount → higher acceptance.
        Anchors: 0% discount → ~10-25% base acceptance; 20% → ~85-95%.
        Adjusted for inventory pressure (excess stock → merchant more willing).
        """
        inventory_pressure = min(1.0, requested_quantity / max(1, available_quantity))

        # Base sigmoid-style acceptance curve
        base_acceptance = 0.10 + 0.85 * (1 - math.exp(-discount_pct / 8.0))

        # Inventory pressure bonus: if we have lots of stock, buyer expects better deal
        # High pressure (quantity ≈ available) → merchant wants to move stock faster
        pressure_bonus = 0.05 * inventory_pressure

        # If buyer has a private target price and discount gets within 5% of it → boost
        target_bonus = 0.0
        if private_target_price_minor and base_price_minor > 0:
            target_pct = (1 - private_target_price_minor / base_price_minor) * 100
            if discount_pct >= target_pct - 2:
                target_bonus = 0.08

        raw = min(0.97, base_acceptance + pressure_bonus + target_bonus)
        return round(raw, 4)

    @classmethod
    def optimize(
        cls,
        rfq: dict,
        product: dict,
        policy: dict | None,
        inventory: dict,
    ) -> dict[str, Any]:
        """
        Returns: {
          recommended_discount_pct, recommended_unit_price_minor, candidates: [...],
          reasoning, constraints_applied, model_type
        }
        """
        base_price = int(product.get("base_price_minor") or 0)
        category = product.get("category") or "General"
        cost_ratio = cls._cost_ratio(category)
        cost_per_unit = int(base_price * cost_ratio)
        quantity = int(rfq.get("requested_quantity") or 1)
        available = int(inventory.get("available_quantity") or 0)
        bulk_reserved = int(inventory.get("bulk_reserved_quantity") or 0)
        atp = max(0, available - bulk_reserved)  # available-to-promise

        # Policy constraints (merchant-approved, never exposed to buyer)
        max_discount_pct = float((policy or {}).get("max_discount_percent") or 20.0)
        min_margin_pct = float((policy or {}).get("min_margin_percent") or 15.0)
        max_autonomous_value = int((policy or {}).get("max_autonomous_order_value_minor") or 10_000_000)

        # Absolute floor: price must cover cost + min margin
        if base_price > 0:
            floor_price = int(cost_per_unit / (1 - min_margin_pct / 100))
        else:
            floor_price = 0

        min_allowed_price = max(floor_price, int(base_price * (1 - max_discount_pct / 100)))

        private_target = rfq.get("private_target_unit_price_minor")
        candidates = []

        for disc_pct in cls.DISCOUNT_CANDIDATES:
            unit_price = int(base_price * (1 - disc_pct / 100))
            total_value = unit_price * quantity

            # Constraint checks
            if unit_price < min_allowed_price:
                candidates.append({
                    "discount_pct": disc_pct,
                    "unit_price_minor": unit_price,
                    "total_value_minor": total_value,
                    "feasible": False,
                    "blocked_reason": "BELOW_FLOOR_PRICE",
                    "acceptance_probability_heuristic": None,
                    "contribution_margin_minor": None,
                    "expected_economic_value": None,
                })
                continue

            if total_value > max_autonomous_value:
                feasibility = "REQUIRES_MERCHANT_APPROVAL"
            elif quantity > atp:
                feasibility = "INSUFFICIENT_INVENTORY"
            else:
                feasibility = "OK"

            acceptance_prob = cls._heuristic_acceptance_probability(
                disc_pct, quantity, available, base_price, private_target
            )
            contribution_per_unit = unit_price - cost_per_unit
            contribution_total = contribution_per_unit * quantity
            # Inventory clearance benefit: excess stock has carrying cost ~2% of value/month
            excess = max(0, available - bulk_reserved - quantity)
            clearance_benefit = int(excess * base_price * 0.02 * (quantity / max(1, available)))

            eev = int(acceptance_prob * contribution_total) + clearance_benefit

            candidates.append({
                "discount_pct": round(disc_pct, 2),
                "unit_price_minor": unit_price,
                "unit_price_inr": round(unit_price / 100, 2),
                "total_value_minor": total_value,
                "total_value_inr": round(total_value / 100, 2),
                "feasible": feasibility == "OK",
                "feasibility": feasibility,
                "acceptance_probability_heuristic": acceptance_prob,
                "contribution_margin_minor": contribution_total,
                "clearance_benefit_minor": clearance_benefit,
                "expected_economic_value": eev,
            })

        # Pick candidate with highest EEV that is feasible
        feasible = [c for c in candidates if c.get("feasible")]
        if not feasible:
            # Relax to REQUIRES_MERCHANT_APPROVAL if no fully feasible option
            feasible = [c for c in candidates if c.get("feasibility") in ("OK", "REQUIRES_MERCHANT_APPROVAL")]

        if not feasible:
            recommended = None
            reasoning = "No feasible discount found within policy constraints."
        else:
            recommended = max(feasible, key=lambda c: c.get("expected_economic_value") or 0)
            reasoning = (
                f"Optimised for Expected Economic Value (contribution margin × acceptance probability + "
                f"inventory clearance benefit). Selected {recommended['discount_pct']}% discount. "
                f"Model type: HEURISTIC — no historical training data. "
                f"Acceptance probability is a sigmoid approximation based on discount depth, "
                f"inventory pressure ({quantity}/{available} units), and policy bounds."
            )

        return {
            "model_type": "HEURISTIC",
            "model_label": "Deterministic heuristic — not a trained ML model",
            "product_id": str(product.get("id")),
            "base_price_minor": base_price,
            "cost_ratio_assumed": cost_ratio,
            "cost_per_unit_minor": cost_per_unit,
            "available_to_promise": atp,
            "constraints_applied": {
                "max_discount_pct": max_discount_pct,
                "min_margin_pct": min_margin_pct,
                "floor_price_minor": min_allowed_price,
                "max_autonomous_order_value_minor": max_autonomous_value,
            },
            "candidates": candidates,
            "recommended_discount_pct": recommended["discount_pct"] if recommended else None,
            "recommended_unit_price_minor": recommended["unit_price_minor"] if recommended else None,
            "recommended_unit_price_inr": recommended["unit_price_inr"] if recommended else None,
            "recommended_total_minor": recommended["total_value_minor"] if recommended else None,
            "recommended_acceptance_probability": recommended["acceptance_probability_heuristic"] if recommended else None,
            "requires_merchant_approval": (recommended or {}).get("feasibility") == "REQUIRES_MERCHANT_APPROVAL",
            "reasoning": reasoning,
        }


# ─────────────────────────────────────────────────────────────────────────────
# BULK POLICY ENGINE
# ─────────────────────────────────────────────────────────────────────────────

class BulkPolicyEngine:
    """Generates AI-recommended quantity-tiered bulk policy rules."""

    @classmethod
    def recommend(
        cls,
        product: dict,
        inventory: dict,
        merchant_id: UUID,
    ) -> dict[str, Any]:
        base_price = int(product.get("base_price_minor") or 0)
        available = int(inventory.get("available_quantity") or 0)
        bulk_min = int(product.get("bulk_min_quantity") or 50)

        # Signal-based tiers
        tiers = []
        if bulk_min > 0:
            tiers.append({"min_qty": 1, "max_qty": bulk_min - 1, "label": "Retail", "max_discount_pct": 0})

        inventory_factor = min(1.0, available / max(1, bulk_min * 5))
        base_max_discount = 8.0 + 10.0 * inventory_factor  # 8-18% depending on excess

        quantity_tiers = [
            (bulk_min, bulk_min * 2 - 1, base_max_discount * 0.4),
            (bulk_min * 2, bulk_min * 5 - 1, base_max_discount * 0.65),
            (bulk_min * 5, bulk_min * 10 - 1, base_max_discount * 0.85),
            (bulk_min * 10, None, base_max_discount),
        ]
        for min_q, max_q, disc in quantity_tiers:
            if min_q <= available:
                tiers.append({
                    "min_qty": min_q,
                    "max_qty": max_q,
                    "label": f"{min_q}–{max_q}" if max_q else f"{min_q}+",
                    "max_discount_pct": round(disc, 1),
                })

        min_margin = 15.0
        max_autonomous_value = min(100_000_00, base_price * bulk_min * 5)  # paise
        max_inventory_alloc = 60.0

        return {
            "product_id": str(product.get("id")),
            "merchant_id": str(merchant_id),
            "tiers": tiers,
            "min_margin_percent": min_margin,
            "max_autonomous_order_value_minor": max_autonomous_value,
            "max_autonomous_order_value_inr": round(max_autonomous_value / 100, 2),
            "max_inventory_allocation_percent": max_inventory_alloc,
            "reservation_duration_minutes": 15,
            "policy_review_hours": 24,
            "reasoning": (
                f"Generated from inventory signals: {available} units available, "
                f"bulk threshold at {bulk_min} units. Higher inventory excess → "
                f"more aggressive discount tiers. Max discount {round(base_max_discount, 1)}% "
                f"based on estimated inventory pressure factor {round(inventory_factor, 2)}. "
                f"Model: HEURISTIC — requires merchant review and approval before activation."
            ),
        }


# ─────────────────────────────────────────────────────────────────────────────
# BUYER BULK AGENT
# ─────────────────────────────────────────────────────────────────────────────

class BuyerBulkAgent:
    """
    Evaluates a merchant quote from the buyer's perspective.
    Private constraints (budget, target price) NEVER leave this class.
    Only the accept/counter/reject decision + counter-offer price are returned.
    """

    @classmethod
    def evaluate_quote(
        cls,
        rfq: dict,
        offered_unit_price_minor: int,
        offered_quantity: int,
        negotiation_round: int,
        max_rounds: int = 3,
    ) -> dict[str, Any]:
        # Private buyer constraints — never exposed externally
        _private_max_budget = rfq.get("private_max_budget_minor")
        _private_target = rfq.get("private_target_unit_price_minor")

        requested_qty = rfq.get("requested_quantity", offered_quantity)
        total_offer = offered_unit_price_minor * offered_quantity

        # Check absolute budget constraint (private)
        if _private_max_budget and total_offer > _private_max_budget:
            # Counter-offer at budget boundary (but don't reveal budget amount)
            counter_price = int(_private_max_budget / max(1, requested_qty))
            return {
                "decision": "COUNTER",
                "counter_unit_price_minor": counter_price,
                "counter_unit_price_inr": round(counter_price / 100, 2),
                "reason": "PRICE_TOO_HIGH",
                # Privacy: do NOT include private_max_budget in response
            }

        # Use target price to determine if we accept or counter
        if _private_target:
            if offered_unit_price_minor <= _private_target:
                return {"decision": "ACCEPT", "reason": "MEETS_TARGET"}
            elif negotiation_round >= max_rounds:
                # Last round — accept if within 8% of target
                gap_pct = (offered_unit_price_minor - _private_target) / max(1, _private_target) * 100
                if gap_pct <= 8.0:
                    return {"decision": "ACCEPT", "reason": "ACCEPTABLE_GAP_LAST_ROUND"}
                return {"decision": "REJECT", "reason": "PRICE_UNACCEPTABLE_FINAL_ROUND"}
            else:
                # Counter midway between offered and target
                counter = int((_private_target + offered_unit_price_minor) / 2)
                return {
                    "decision": "COUNTER",
                    "counter_unit_price_minor": counter,
                    "counter_unit_price_inr": round(counter / 100, 2),
                    "reason": "SPLITTING_DIFFERENCE",
                }
        else:
            # No explicit target — use budget awareness
            if negotiation_round >= max_rounds:
                return {"decision": "ACCEPT", "reason": "FINAL_ROUND_ACCEPT"}
            # Generic counter: ask for 3-5% more off
            counter = int(offered_unit_price_minor * 0.965)
            return {
                "decision": "COUNTER",
                "counter_unit_price_minor": counter,
                "counter_unit_price_inr": round(counter / 100, 2),
                "reason": "SEEKING_BETTER_PRICE",
            }


# ─────────────────────────────────────────────────────────────────────────────
# MERCHANT BULK AGENT
# ─────────────────────────────────────────────────────────────────────────────

class MerchantBulkAgent:
    """
    Generates quote or counter-offer within approved policy bounds.
    Floor price and cost structure are NEVER returned in public API responses.
    """

    @classmethod
    def generate_initial_quote(
        cls,
        rfq: dict,
        optimization_result: dict,
        policy: dict | None,
    ) -> dict[str, Any]:
        """Open with the AI-recommended price (not immediately the floor)."""
        rec_price = optimization_result.get("recommended_unit_price_minor")
        quantity = rfq.get("requested_quantity", 1)

        if not rec_price:
            return {"error": "No feasible quote could be generated"}

        total = rec_price * quantity
        return {
            "unit_price_minor": rec_price,
            "unit_price_inr": round(rec_price / 100, 2),
            "quantity": quantity,
            "total_minor": total,
            "total_inr": round(total / 100, 2),
            "requires_merchant_approval": optimization_result.get("requires_merchant_approval", False),
            "optimization_reasoning": optimization_result.get("reasoning"),
            # Floor price intentionally NOT included
        }

    @classmethod
    def evaluate_counter(
        cls,
        counter_unit_price_minor: int,
        quantity: int,
        policy: dict | None,
        optimization_result: dict,
        negotiation_round: int,
        max_rounds: int = 3,
    ) -> dict[str, Any]:
        """
        Decides whether to accept, counter, or reject buyer's counter-offer.
        Floor price never exposed in response.
        """
        constraints = optimization_result.get("constraints_applied", {})
        floor_price = constraints.get("floor_price_minor", 0)  # private
        rec_price = optimization_result.get("recommended_unit_price_minor", counter_unit_price_minor)

        if counter_unit_price_minor < floor_price:
            # Below floor — never reveal floor, just reject or counter at min feasible
            if negotiation_round >= max_rounds:
                return {"decision": "REJECT", "reason": "PRICE_BELOW_ACCEPTABLE_MINIMUM"}
            # Counter at midpoint between counter and recommended (still above floor)
            mid = int((rec_price + counter_unit_price_minor) / 2)
            mid = max(mid, floor_price)
            return {
                "decision": "COUNTER",
                "unit_price_minor": mid,
                "unit_price_inr": round(mid / 100, 2),
                "total_minor": mid * quantity,
                "total_inr": round(mid * quantity / 100, 2),
                "reason": "MINIMUM_ECONOMICS_REQUIRED",
                # Floor NOT exposed
            }

        # Counter is above floor — check if acceptable
        gap_from_rec = (rec_price - counter_unit_price_minor) / max(1, rec_price)

        if gap_from_rec <= 0.03 or negotiation_round >= max_rounds:
            # Within 3% of recommendation, or last round → accept
            return {
                "decision": "ACCEPT",
                "unit_price_minor": counter_unit_price_minor,
                "unit_price_inr": round(counter_unit_price_minor / 100, 2),
                "total_minor": counter_unit_price_minor * quantity,
                "total_inr": round(counter_unit_price_minor * quantity / 100, 2),
                "reason": "ACCEPTABLE_COUNTER",
            }

        # Split the difference
        split_price = int((rec_price + counter_unit_price_minor) / 2)
        split_price = max(split_price, floor_price)
        return {
            "decision": "COUNTER",
            "unit_price_minor": split_price,
            "unit_price_inr": round(split_price / 100, 2),
            "total_minor": split_price * quantity,
            "total_inr": round(split_price * quantity / 100, 2),
            "reason": "SPLITTING_DIFFERENCE",
        }


# ─────────────────────────────────────────────────────────────────────────────
# INVENTORY RESERVATION SERVICE
# ─────────────────────────────────────────────────────────────────────────────

class InventoryReservationService:
    """
    Atomic inventory reservation with TTL.
    Uses SELECT FOR UPDATE to prevent overselling.
    """

    @staticmethod
    def available_to_promise(db: Session, product_id: UUID, merchant_id: UUID) -> int:
        """Returns ATP = physical_inventory - active_bulk_reservations."""
        row = db.execute(
            text("""
                SELECT
                    COALESCE(mi.available_quantity, 0) AS physical,
                    COALESCE((
                        SELECT SUM(ir.quantity)
                        FROM inventory_reservations ir
                        WHERE ir.product_id = :pid
                          AND ir.status = 'ACTIVE'
                          AND ir.expires_at > now()
                    ), 0) AS reserved
                FROM merchant_inventory mi
                WHERE mi.product_id = :pid AND mi.merchant_id = :mid
            """),
            {"pid": product_id, "mid": merchant_id},
        ).mappings().one_or_none()

        if not row:
            return 0
        return max(0, int(row["physical"]) - int(row["reserved"]))

    @staticmethod
    def reserve(
        db: Session,
        product_id: UUID,
        merchant_id: UUID,
        quantity: int,
        rfq_id: UUID,
        negotiation_id: UUID,
        duration_minutes: int = 15,
    ) -> dict:
        """
        Atomically checks ATP and creates reservation.
        Raises ValueError if insufficient inventory.
        """
        # Lock the inventory row to prevent concurrent over-reservation
        inv_row = db.execute(
            text("""
                SELECT mi.available_quantity,
                       COALESCE((
                           SELECT SUM(ir.quantity)
                           FROM inventory_reservations ir
                           WHERE ir.product_id = :pid
                             AND ir.status = 'ACTIVE'
                             AND ir.expires_at > now()
                       ), 0) AS active_reserved
                FROM merchant_inventory mi
                WHERE mi.product_id = :pid AND mi.merchant_id = :mid
                FOR UPDATE
            """),
            {"pid": product_id, "mid": merchant_id},
        ).mappings().one_or_none()

        if not inv_row:
            raise ValueError("Product inventory record not found")

        atp = max(0, int(inv_row["available_quantity"]) - int(inv_row["active_reserved"]))
        if quantity > atp:
            raise ValueError(
                f"Insufficient inventory: {atp} units available-to-promise, {quantity} requested"
            )

        expires_at = datetime.now(UTC) + timedelta(minutes=duration_minutes)
        reservation = db.execute(
            text("""
                INSERT INTO inventory_reservations
                    (product_id, merchant_id, rfq_id, negotiation_id, quantity, status, expires_at)
                VALUES (:pid, :mid, :rfq, :neg, :qty, 'ACTIVE', :exp)
                RETURNING id, quantity, status, expires_at, created_at
            """),
            {
                "pid": product_id,
                "mid": merchant_id,
                "rfq": rfq_id,
                "neg": negotiation_id,
                "qty": quantity,
                "exp": expires_at,
            },
        ).mappings().one()

        return {
            "reservation_id": str(reservation["id"]),
            "quantity": quantity,
            "status": "ACTIVE",
            "expires_at": reservation["expires_at"].isoformat(),
            "expires_in_minutes": duration_minutes,
        }

    @staticmethod
    def release(db: Session, reservation_id: UUID) -> None:
        db.execute(
            text("""
                UPDATE inventory_reservations
                SET status = 'RELEASED', updated_at = now()
                WHERE id = :rid AND status = 'ACTIVE'
            """),
            {"rid": reservation_id},
        )

    @staticmethod
    def convert(db: Session, reservation_id: UUID, transaction_id: UUID) -> None:
        """Called on successful payment capture."""
        db.execute(
            text("""
                UPDATE inventory_reservations
                SET status = 'CONVERTED', order_id = :txn, updated_at = now()
                WHERE id = :rid AND status = 'ACTIVE'
            """),
            {"rid": reservation_id, "txn": transaction_id},
        )
        # Also decrement physical inventory
        db.execute(
            text("""
                UPDATE merchant_inventory mi
                SET available_quantity = GREATEST(0, mi.available_quantity - ir.quantity),
                    updated_at = now()
                FROM inventory_reservations ir
                WHERE ir.id = :rid AND mi.product_id = ir.product_id
            """),
            {"rid": reservation_id},
        )

    @staticmethod
    def expire_stale(db: Session) -> int:
        """Expire reservations past their TTL. Call from a background job."""
        result = db.execute(
            text("""
                UPDATE inventory_reservations
                SET status = 'EXPIRED', updated_at = now()
                WHERE status = 'ACTIVE' AND expires_at < now()
            """)
        )
        db.commit()
        return result.rowcount


# ─────────────────────────────────────────────────────────────────────────────
# BULK OPPORTUNITY DETECTOR (Revenue Intelligence)
# ─────────────────────────────────────────────────────────────────────────────

class BulkOpportunityDetector:
    """Detects bulk revenue opportunities from inventory signals."""

    @classmethod
    def detect(cls, db: Session, merchant_id: UUID) -> list[dict]:
        products = db.execute(
            text("""
                SELECT p.id, p.name, p.category, p.base_price_minor,
                       p.bulk_enabled, p.bulk_min_quantity,
                       COALESCE(mi.available_quantity, 0) AS available_quantity,
                       COALESCE(mi.bulk_reserved_quantity, 0) AS bulk_reserved,
                       COALESCE((
                           SELECT SUM(ir.quantity)
                           FROM inventory_reservations ir
                           WHERE ir.product_id = p.id AND ir.status = 'ACTIVE'
                             AND ir.expires_at > now()
                       ), 0) AS active_reservations
                FROM merchant_products p
                LEFT JOIN merchant_inventory mi ON mi.product_id = p.id
                WHERE p.merchant_id = :mid AND p.active
                ORDER BY COALESCE(mi.available_quantity, 0) DESC
            """),
            {"mid": merchant_id},
        ).mappings().fetchall()

        opportunities = []
        for p in products:
            available = int(p["available_quantity"])
            bulk_min = int(p["bulk_min_quantity"] or 50)
            base_price = int(p["base_price_minor"] or 0)

            if available < bulk_min:
                continue

            # Estimate 30-day retail forecast (heuristic: 20% of available/month)
            forecast_30d = max(1, int(available * 0.20))
            excess = max(0, available - forecast_30d)

            if excess < bulk_min:
                continue

            # Suggested bulk range
            min_bulk = bulk_min
            max_bulk = min(excess, bulk_min * 15)
            rec_opening_price = int(base_price * 0.86)  # ~14% discount opening
            exp_settlement_low = int(base_price * 0.83)
            exp_settlement_high = int(base_price * 0.88)

            has_data = False  # Would be True if historical bulk orders existed
            confidence = "MEDIUM" if available > bulk_min * 3 else "LOW"

            opportunities.append({
                "product_id": str(p["id"]),
                "product_name": p["name"],
                "category": p["category"],
                "base_price_minor": base_price,
                "base_price_inr": round(base_price / 100, 2),
                "available_quantity": available,
                "forecast_30d_retail": forecast_30d,
                "estimated_excess": excess,
                "suggested_bulk_range": {"min": min_bulk, "max": max_bulk},
                "recommended_opening_price_minor": rec_opening_price,
                "recommended_opening_price_inr": round(rec_opening_price / 100, 2),
                "expected_settlement_range_inr": {
                    "low": round(exp_settlement_low / 100, 2),
                    "high": round(exp_settlement_high / 100, 2),
                },
                "estimated_revenue_range_inr": {
                    "low": round(exp_settlement_low * min_bulk / 100, 2),
                    "high": round(exp_settlement_high * max_bulk / 100, 2),
                },
                "confidence": confidence,
                "historical_data_available": has_data,
                "note": "HEURISTIC — estimates based on inventory signals, not historical bulk data",
            })

        return opportunities
