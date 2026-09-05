from datetime import UTC, datetime

from app.schemas.negotiation import (
    NegotiationActor,
    NegotiationDecision,
    NegotiationState,
    NegotiationStatus,
)


class NegotiationController:
    """Owns every numeric boundary; model output can supply wording but not authority."""

    @staticmethod
    def _fallback_valid(state: NegotiationState, now: datetime) -> bool:
        return (
            state.fallback_price_minor is not None
            and state.fallback_valid_until is not None
            and state.fallback_valid_until > now
        )

    def step(
        self,
        state: NegotiationState,
        actor: NegotiationActor,
        proposed_amount_minor: int,
        now: datetime | None = None,
    ) -> tuple[NegotiationState, NegotiationDecision]:
        current_time = now or datetime.now(UTC)
        if state.status != NegotiationStatus.OPEN:
            raise ValueError("Negotiation session is closed")
        if state.expires_at <= current_time:
            updated = state.model_copy(update={"status": NegotiationStatus.EXPIRED})
            return updated, NegotiationDecision(
                decision="EXPIRE",
                status=updated.status,
                reason_code="SESSION_EXPIRED",
                current_round=state.current_round,
            )
        if state.merchant_floor_minor > state.buyer_ceiling_minor:
            updated = state.model_copy(update={"status": NegotiationStatus.REJECTED})
            return updated, NegotiationDecision(
                decision="REJECT",
                status=updated.status,
                reason_code="NO_OVERLAPPING_RANGE",
                current_round=state.current_round,
            )
        if (
            actor == NegotiationActor.BUYER_AGENT
            and not 0 <= proposed_amount_minor <= state.buyer_ceiling_minor
        ):
            return state, NegotiationDecision(
                decision="BLOCK",
                status=state.status,
                reason_code="BUYER_CEILING_VIOLATION",
                current_round=state.current_round,
            )
        if (
            actor == NegotiationActor.MERCHANT_AGENT
            and not state.merchant_floor_minor
            <= proposed_amount_minor
            <= state.starting_price_minor
        ):
            return state, NegotiationDecision(
                decision="BLOCK",
                status=state.status,
                reason_code="MERCHANT_FLOOR_VIOLATION",
                current_round=state.current_round,
            )
        next_round = state.current_round + 1
        changes: dict = {"current_round": next_round}
        accepted: int | None = None
        if actor == NegotiationActor.BUYER_AGENT:
            changes["last_buyer_offer_minor"] = proposed_amount_minor
            if (
                state.last_merchant_ask_minor is not None
                and proposed_amount_minor >= state.last_merchant_ask_minor
            ):
                accepted = state.last_merchant_ask_minor
        else:
            changes["last_merchant_ask_minor"] = proposed_amount_minor
            if (
                state.last_buyer_offer_minor is not None
                and proposed_amount_minor <= state.last_buyer_offer_minor
            ):
                accepted = proposed_amount_minor
        fallback_valid = self._fallback_valid(state, current_time)
        if accepted is not None:
            if fallback_valid and accepted > state.fallback_price_minor:
                changes.update(
                    status=NegotiationStatus.FALLBACK,
                    final_agreed_price_minor=state.fallback_price_minor,
                )
                updated = state.model_copy(update=changes)
                return updated, NegotiationDecision(
                    decision="FALLBACK",
                    status=updated.status,
                    accepted_price_minor=state.fallback_price_minor,
                    reason_code="FALLBACK_BETTER_THAN_AGREEMENT",
                    current_round=next_round,
                )
            changes.update(status=NegotiationStatus.ACCEPTED, final_agreed_price_minor=accepted)
            updated = state.model_copy(update=changes)
            return updated, NegotiationDecision(
                decision="ACCEPT",
                status=updated.status,
                accepted_price_minor=accepted,
                reason_code="BOUNDED_OVERLAP_ACCEPTED",
                current_round=next_round,
            )
        if next_round >= state.max_rounds:
            if fallback_valid:
                changes.update(
                    status=NegotiationStatus.FALLBACK,
                    final_agreed_price_minor=state.fallback_price_minor,
                )
                updated = state.model_copy(update=changes)
                return updated, NegotiationDecision(
                    decision="FALLBACK",
                    status=updated.status,
                    accepted_price_minor=state.fallback_price_minor,
                    reason_code="MAX_ROUNDS_FALLBACK",
                    current_round=next_round,
                )
            changes["status"] = NegotiationStatus.REJECTED
            updated = state.model_copy(update=changes)
            return updated, NegotiationDecision(
                decision="REJECT",
                status=updated.status,
                reason_code="MAX_ROUNDS_NO_DEAL",
                current_round=next_round,
            )
        updated = state.model_copy(update=changes)
        return updated, NegotiationDecision(
            decision="CONTINUE",
            status=updated.status,
            reason_code="BOUNDS_VALID_CONTINUE",
            current_round=next_round,
        )


class BasketGrowthEngine:
    @staticmethod
    def eligible(
        relationships: list[dict],
        relationship_type: str,
        permission: bool,
        remaining_budget_minor: int,
        remaining_quantity: int,
    ) -> list[dict]:
        if not permission or remaining_quantity <= 0:
            return []
        candidates = []
        for row in relationships:
            if (
                row["relationship_type"] != relationship_type
                or not row["active"]
                or row["inventory_available"] <= 0
                or row["price_minor"] > remaining_budget_minor
            ):
                continue
            candidates.append(
                {
                    "source_product_id": row["source_product_id"],
                    "offered_product_id": row["offered_product_id"],
                    "name": row["name"],
                    "price_minor": row["price_minor"],
                    "currency": row["currency"],
                    "relationship_type": relationship_type,
                    "requires_confirmation": True,
                    "authority_source": "MERCHANT_CATALOG",
                }
            )
        return sorted(candidates, key=lambda item: item["price_minor"])

    @staticmethod
    def validate_selection(offered_product_id, eligible_candidates: list[dict]) -> dict:
        selected = next(
            (
                row
                for row in eligible_candidates
                if str(row["offered_product_id"]) == str(offered_product_id)
            ),
            None,
        )
        if not selected:
            raise ValueError("Model/user selection is not an eligible catalog authority")
        return selected
