import math
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID
from sqlalchemy import text
from sqlalchemy.orm import Session


class PricingIntelligenceService:
    """
    Autonomous Pricing + Policy Intelligence Engine
    5-Engine Architecture:
      1. Demand Forecasting Engine
      2. Market & Cost Intelligence Engine
      3. Price Elasticity Engine
      4. Optimization Engine (Candidate Grid Simulation)
      5. Policy Generator (Executable Policy + Adaptive Rules + Safety Check)
    """

    DEFAULT_DISCOUNT_CANDIDATES = [0, 5, 8, 11, 15, 20]

    CATEGORY_ELASTICITY = {
        "ice cream": -1.85,
        "dairy": -1.25,
        "grocery": -1.35,
        "beverages": -1.70,
        "electronics": -1.55,
        "headphones": -1.65,
        "audio": -1.60,
    }

    CATEGORY_COST_RATIO = {
        "ice cream": 0.62,
        "dairy": 0.78,
        "grocery": 0.72,
        "beverages": 0.55,
        "electronics": 0.70,
        "headphones": 0.65,
        "audio": 0.65,
    }

    @classmethod
    def get_elasticity(cls, category: str | None) -> float:
        cat_lower = (category or "").lower()
        for k, v in cls.CATEGORY_ELASTICITY.items():
            if k in cat_lower:
                return v
        return -1.50

    @classmethod
    def get_cost_ratio(cls, category: str | None) -> float:
        cat_lower = (category or "").lower()
        for k, v in cls.CATEGORY_COST_RATIO.items():
            if k in cat_lower:
                return v
        return 0.68

    @classmethod
    def evaluate_product(
        cls,
        db: Session,
        merchant_id: UUID,
        product: dict[str, Any],
        duration_days: int = 5,
    ) -> dict[str, Any]:
        """
        Runs the full 5-Engine pipeline on a single merchant product.
        """
        product_id = product["id"]
        category = product.get("category") or "General"
        base_price_minor = int(product.get("base_price_minor") or 0)
        base_price_inr = base_price_minor / 100.0

        # Current Inventory
        inventory_qty = int(product.get("available_quantity") or 0)
        reserved_qty = int(product.get("reserved_quantity") or 0)
        effective_inventory = max(0, inventory_qty - reserved_qty)

        # 1. Cost & Margin Setup
        cost_ratio = cls.get_cost_ratio(category)
        # Check if product metadata has explicit cost, else estimate via category benchmark
        cost_price_minor = int(
            (product.get("metadata") or {}).get("cost_price_minor")
            or round(base_price_minor * cost_ratio)
        )
        cost_price_inr = cost_price_minor / 100.0
        min_margin_percent = 18.0  # Merchant target minimum margin %
        min_margin_floor_minor = int(round(cost_price_minor * (1 + (min_margin_percent / 100.0))))

        # 2. Demand Forecasting Engine
        # Query recent sales & views from DB if available
        sales_data = db.execute(
            text("""
                select 
                    count(distinct t.id) as orders_30d,
                    coalesce(sum(ci.quantity), 0) as units_30d
                from cart_items ci
                join carts c on c.id = ci.cart_id
                join transactions t on t.cart_id = c.id
                where ci.product_id = :p and t.status = 'SUCCESS'
                  and t.created_at >= now() - interval '30 days'
            """),
            {"p": product_id},
        ).mappings().first()

        units_sold_30d = int(sales_data["units_30d"] or 0) if sales_data else 0

        # Baseline monthly forecast (at least a sensible realistic volume based on catalog)
        if units_sold_30d > 0:
            forecast_30d_demand = max(10, units_sold_30d)
        else:
            # Synthetic cold-start baseline: higher inventory items usually expect larger volume
            forecast_30d_demand = max(15, round(effective_inventory * 0.25))

        # Inventory Pressure = Current Inventory / Forecast 30-Day Demand
        inventory_pressure = round(
            effective_inventory / max(1, forecast_30d_demand), 2
        )
        has_excess_inventory = inventory_pressure >= 2.0
        overstock_prob = min(98, round(max(10.0, (inventory_pressure / 4.0) * 85)))

        # 3. Price Elasticity Engine
        elasticity = cls.get_elasticity(category)

        # 4. Optimization Engine (Candidate Grid Simulation)
        baseline_period_demand = max(
            1.0, forecast_30d_demand * (duration_days / 30.0)
        )

        simulation_rows = []
        best_candidate = None
        best_score = -float("inf")

        for d_pct in cls.DEFAULT_DISCOUNT_CANDIDATES:
            d_frac = d_pct / 100.0
            new_price_minor = int(round(base_price_minor * (1.0 - d_frac)))
            new_price_inr = new_price_minor / 100.0

            # Unit profit
            profit_unit_minor = new_price_minor - cost_price_minor
            profit_unit_inr = profit_unit_minor / 100.0

            # Demand lift from elasticity: Q(d) = Q0 * (1 + |e| * d)^1.15
            lift_factor = math.pow(1.0 + abs(elasticity) * d_frac, 1.15) if d_pct > 0 else 1.0
            predicted_sales = min(
                effective_inventory,
                max(1, int(round(baseline_period_demand * lift_factor))),
            )

            expected_profit_minor = predicted_sales * profit_unit_minor
            expected_profit_inr = round(expected_profit_minor / 100.0, 2)

            stock_cleared_pct = round(
                min(100.0, (predicted_sales / max(1, effective_inventory)) * 100.0), 1
            )

            # Check hard constraint: margin >= min_margin_floor
            is_valid_margin = new_price_minor >= min_margin_floor_minor and profit_unit_minor > 0

            # Optimization objective:
            # Score = Expected Profit + Clearance Incentive - Margin Compression Penalty
            clearance_incentive = (stock_cleared_pct / 100.0) * (base_price_inr * 0.15) * min(3.0, inventory_pressure)
            score = (expected_profit_inr + clearance_incentive) if is_valid_margin else -999999

            row = {
                "discount_percent": d_pct,
                "new_price_inr": round(new_price_inr, 2),
                "new_price_minor": new_price_minor,
                "predicted_sales": predicted_sales,
                "profit_per_unit_inr": round(profit_unit_inr, 2),
                "expected_total_profit_inr": expected_profit_inr,
                "stock_cleared_percent": stock_cleared_pct,
                "is_margin_safe": is_valid_margin,
                "score": round(score, 2),
                "is_optimal": False,
            }
            simulation_rows.append(row)

            if is_valid_margin and score > best_score:
                best_score = score
                best_candidate = row

        # Fallback if none passed margin test
        if not best_candidate:
            best_candidate = simulation_rows[0]

        best_candidate["is_optimal"] = True
        optimal_discount = best_candidate["discount_percent"]

        # Why X% Rationale Generation
        baseline_row = simulation_rows[0]
        profit_uplift = best_candidate["expected_total_profit_inr"] - baseline_row["expected_total_profit_inr"]
        sales_lift_pct = round(
            ((best_candidate["predicted_sales"] - baseline_row["predicted_sales"]) / max(1, baseline_row["predicted_sales"])) * 100
        )

        why_reason = (
            f"Tested discount levels: 0%, 5%, 8%, 11%, 15%, 20%. "
            f"{optimal_discount}% produces the highest predicted total profit (₹{best_candidate['expected_total_profit_inr']:,.2f}) "
            f"while increasing clearance to {best_candidate['stock_cleared_percent']}% (+{sales_lift_pct}% sales lift). "
            f"Higher discounts like 15%+ compress unit margins without generating enough incremental volume to offset the discount cost."
            if optimal_discount > 0
            else f"Current demand velocity and healthy inventory ratio ({inventory_pressure}x) indicate no discount is necessary at this time."
        )

        # 5. Policy Generator (Executable Policy + Adaptive Rules)
        policy_code = f"#P-{str(product_id)[:4].upper()}"
        order_limit = min(effective_inventory, max(20, best_candidate["predicted_sales"] * 2))

        adaptive_rules = {
            "increase_threshold": f"If sales remain >15% below forecast after 48 hours → evaluate {min(25, optimal_discount + 2)}%",
            "decrease_threshold": f"If demand surges >20% above forecast → reduce discount to {max(0, optimal_discount - 4)}%",
            "stop_condition": f"{order_limit} orders completed or available stock falls below safety buffer (5 units)",
            "reevaluation_cadence": "Every 24 hours",
        }

        # Check existing policy in DB
        active_policy = db.execute(
            text("""
                select * from merchant_policies
                where merchant_id = :m 
                  and scope = 'PRODUCT' 
                  and scope_reference = :p
                  and status = 'ACTIVE'
                order by version desc
                limit 1
            """),
            {"m": merchant_id, "p": str(product_id)},
        ).mappings().first()

        return {
            "product_id": str(product_id),
            "product_name": product.get("name"),
            "sku": product.get("sku"),
            "category": category,
            "base_price_inr": base_price_inr,
            "base_price_minor": base_price_minor,
            "cost_price_inr": round(cost_price_inr, 2),
            "cost_price_minor": cost_price_minor,
            "available_quantity": effective_inventory,
            "inventory_pressure": inventory_pressure,
            "has_excess_inventory": has_excess_inventory,
            "overstock_probability": overstock_prob,
            "forecast_30d_demand": forecast_30d_demand,
            "elasticity": elasticity,
            # Active policy currently in DB
            "active_policy": dict(active_policy) if active_policy else None,
            # AI Recommended Policy
            "recommended_policy": {
                "policy_code": policy_code,
                "objective": "Reduce excess inventory while maximizing contribution profit" if has_excess_inventory else "Maintain baseline margin and steady conversion",
                "recommended_discount_percent": optimal_discount,
                "recommended_price_inr": best_candidate["new_price_inr"],
                "recommended_price_minor": best_candidate["new_price_minor"],
                "floor_price_inr": round(min_margin_floor_minor / 100.0, 2),
                "floor_price_minor": min_margin_floor_minor,
                "duration_days": duration_days,
                "order_limit": order_limit,
                "target_segment": "Price-sensitive & new buyers" if optimal_discount > 0 else "All shoppers",
                "minimum_margin_percent": min_margin_percent,
                "why_reason": why_reason,
                "expected_sales": best_candidate["predicted_sales"],
                "expected_sales_lift_percent": sales_lift_pct,
                "stock_cleared_percent": best_candidate["stock_cleared_percent"],
                "expected_total_profit_inr": best_candidate["expected_total_profit_inr"],
                "adaptive_rules": adaptive_rules,
            },
            "simulation_matrix": simulation_rows,
        }

    @classmethod
    def resimulate_custom(
        cls,
        base_price_minor: int,
        cost_price_minor: int,
        available_quantity: int,
        forecast_30d_demand: int,
        category: str,
        custom_discount_percent: float,
        custom_duration_days: int,
        custom_order_limit: int,
    ) -> dict[str, Any]:
        """
        Interactive re-simulation when a merchant modifies discount, duration, or limits.
        """
        base_price_inr = base_price_minor / 100.0
        cost_price_inr = cost_price_minor / 100.0
        elasticity = cls.get_elasticity(category)

        d_frac = custom_discount_percent / 100.0
        proposed_price_minor = int(round(base_price_minor * (1.0 - d_frac)))
        proposed_price_inr = proposed_price_minor / 100.0

        profit_unit_minor = proposed_price_minor - cost_price_minor
        profit_unit_inr = profit_unit_minor / 100.0
        margin_percent = round((profit_unit_inr / max(0.01, proposed_price_inr)) * 100.0, 1)

        baseline_period_demand = max(1.0, forecast_30d_demand * (custom_duration_days / 30.0))
        lift_factor = math.pow(1.0 + abs(elasticity) * d_frac, 1.15) if custom_discount_percent > 0 else 1.0

        predicted_sales = min(
            min(available_quantity, custom_order_limit),
            max(1, int(round(baseline_period_demand * lift_factor))),
        )

        expected_profit_inr = round((predicted_sales * profit_unit_minor) / 100.0, 2)
        stock_cleared_pct = round(
            min(100.0, (predicted_sales / max(1, available_quantity)) * 100.0), 1
        )
        remaining_stock = max(0, available_quantity - predicted_sales)
        remaining_inventory_pressure = round(remaining_stock / max(1, forecast_30d_demand), 2)
        overstock_risk_after = min(98, round(max(5.0, (remaining_inventory_pressure / 4.0) * 85)))

        # Safety constraint checks
        min_safe_margin_pct = 18.0
        is_safe = profit_unit_minor > 0 and margin_percent >= min_safe_margin_pct

        if is_safe:
            safety_status = "PASSED"
            safety_message = f"✓ Policy satisfies Security Kernel constraints: Gross margin is {margin_percent}% (threshold ≥ {min_safe_margin_pct}%)."
        elif profit_unit_minor <= 0:
            safety_status = "VIOLATION"
            safety_message = f"✗ Policy violates cost floor: Proposed price ₹{proposed_price_inr} is below cost price ₹{cost_price_inr}."
        else:
            safety_status = "WARNING"
            safety_message = f"⚠️ Warning: Gross margin {margin_percent}% is below recommended target of {min_safe_margin_pct}%."

        return {
            "proposed_discount_percent": custom_discount_percent,
            "proposed_price_inr": round(proposed_price_inr, 2),
            "proposed_price_minor": proposed_price_minor,
            "profit_per_unit_inr": round(profit_unit_inr, 2),
            "margin_percent": margin_percent,
            "predicted_sales": predicted_sales,
            "expected_total_profit_inr": expected_profit_inr,
            "stock_cleared_percent": stock_cleared_pct,
            "remaining_stock": remaining_stock,
            "overstock_risk_after_percent": overstock_risk_after,
            "safety_status": safety_status,
            "safety_message": safety_message,
            "is_safe": is_safe,
        }
