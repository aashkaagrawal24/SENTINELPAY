import base64
import hashlib
import json
import math
import random
import re
import secrets
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from z3 import Int, Optimize, Or, Sum, sat

from app.schemas.advanced import (
    BanditArm,
    BanditContext,
    ExternalOfferInput,
    MultiVerifierRequest,
    ProcurementOptimizeRequest,
)


class ConnectorCapability(StrEnum):
    PUBLIC_SCOUT = "PUBLIC_SCOUT"
    AUTHENTICATED_DISCOVERY = "AUTHENTICATED_DISCOVERY"
    NEGOTIATION_ONLY = "NEGOTIATION_ONLY"
    FULL_AGENTIC = "FULL_AGENTIC"
    HANDOFF = "HANDOFF"


class ExternalConnector(Protocol):
    name: str
    capability: ConnectorCapability

    def search(self, query: str) -> list[ExternalOfferInput]: ...


class StaticEvaluationConnector:
    """Evaluation connector only; supplied snapshots are never represented as live market data."""

    name = "STATIC_EVALUATION"
    capability = ConnectorCapability.HANDOFF

    def __init__(self, offers: list[ExternalOfferInput], fail: bool = False):
        self.offers = offers
        self.fail = fail

    def search(self, query: str) -> list[ExternalOfferInput]:
        del query
        if self.fail:
            raise RuntimeError("Evaluation connector unavailable")
        return self.offers


class ExternalMarketService:
    @staticmethod
    def normalize(value: str) -> str:
        return " ".join(re.findall(r"[a-z0-9]+", value.lower()))

    @classmethod
    def similarity(cls, query: str, title: str) -> float:
        left, right = set(cls.normalize(query).split()), set(cls.normalize(title).split())
        return len(left & right) / len(left | right) if left | right else 0

    def search(
        self, connector: ExternalConnector, query: str, expected_key: str | None = None
    ) -> dict:
        started = time.perf_counter()
        try:
            offers = connector.search(query)
            ranked = sorted(
                (
                    {
                        **offer.model_dump(mode="json"),
                        "normalized_product_key": self.normalize(offer.title),
                        "match_score": round(self.similarity(query, offer.title), 6),
                        "connector": connector.name,
                        "capability": connector.capability,
                        "checkout_capability": "HANDOFF"
                        if connector.capability != ConnectorCapability.FULL_AGENTIC
                        else "FULL_AGENTIC",
                        "provenance": "SIMULATED",
                    }
                    for offer in offers
                ),
                key=lambda item: item["match_score"],
                reverse=True,
            )
            relevant = [item for item in ranked if item["match_score"] >= 0.5]
            precision = (
                sum(
                    expected_key in item["normalized_product_key"]
                    for item in relevant
                )
                / len(relevant)
                if relevant and expected_key
                else None
            )
            freshness = [
                max(
                    0,
                    int(
                        (datetime.now(UTC) - offer.fetched_at.astimezone(UTC)).total_seconds()
                    ),
                )
                for offer in offers
            ]
            return {
                "status": "SUCCESS",
                "offers": ranked,
                "metrics": {
                    "product_match_precision": precision,
                    "average_offer_freshness_seconds": sum(freshness) / len(freshness)
                    if freshness
                    else None,
                    "connector_success_rate": 1.0,
                    "latency_ms": int((time.perf_counter() - started) * 1000),
                },
                "fallback": "HANDOFF",
            }
        except Exception:  # noqa: BLE001 - connectors fail independently and safely.
            return {
                "status": "FALLBACK",
                "offers": [],
                "metrics": {"connector_success_rate": 0.0},
                "fallback": "HANDOFF",
            }


class ContextualBanditService:
    ACTIONS = ("AGGRESSIVE", "BALANCED", "FAST_CLOSE")

    @staticmethod
    def context_key(context: BanditContext) -> str:
        age = "OLD" if context.listing_age_days >= 30 else "NEW"
        budget = "HIGH" if context.remaining_budget_minor >= 100_000 else "LOW"
        return f"{context.category}:{context.seller_type}:{age}:{budget}:{context.prior_rounds}"

    def select(self, context: BanditContext, arms: list[BanditArm]) -> dict:
        valid = [arm for arm in arms if arm.action in self.ACTIONS]
        if not valid:
            return {"action": "BALANCED", "status": "FALLBACK", "reason": "NO_VALID_ARMS"}
        unexplored = next((arm for arm in valid if arm.pulls == 0), None)
        total = max(1, sum(arm.pulls for arm in valid))
        scores = {
            arm.action: (
                math.inf
                if arm.pulls == 0
                else arm.cumulative_reward / arm.pulls
                + math.sqrt(2 * math.log(total) / arm.pulls)
            )
            for arm in valid
        }
        selected = unexplored.action if unexplored else max(scores, key=scores.get)
        return {
            "action": selected,
            "status": "SUCCESS",
            "context_key": self.context_key(context),
            "scores": scores,
            "baseline": "BALANCED",
            "authority_changes": {},
        }

    @staticmethod
    def reward(
        savings_minor: int,
        merchant_revenue_minor: int,
        elapsed_seconds: float,
        failure: bool,
        discount_cost_minor: int,
        alpha: float = 1.0,
        beta: float = 100.0,
    ) -> float:
        return (
            savings_minor
            + merchant_revenue_minor
            - alpha * elapsed_seconds
            - beta * int(failure)
            - discount_cost_minor
        )


class BudgetRangeProofService:
    """Unaudited Pedersen range proof for one narrow sufficiency statement."""

    P = int(
        "FFFFFFFFFFFFFFFFC90FDAA22168C234C4C6628B80DC1CD129024E088A67CC74020BBEA6"
        "3B139B22514A08798E3404DDEF9519B3CD3A431B302B0A6DF25F14374FE1356D"
        "6D51C245E485B576625E7EC6F44C42E9A637ED6B0BFF5CB6F406B7EDEE386BFB"
        "5A899FA5AE9F24117C4B1FE649286651ECE45B3DC2007CB8A163BF0598DA48361"
        "C55D39A69163FA8FD24CF5F83655D23DCA3AD961C62F356208552BB9ED5290770"
        "96966D670C354E4ABC9804F1746C08CA18217C32905E462E36CE3BE39E772C180"
        "E86039B2783A2EC07A28FB5C55DF06F4C52C9DE2BCBF6955817183995497CEA956"
        "AE515D2261898FA051015728E5A8AACAA68FFFFFFFFFFFFFFFF",
        16,
    )
    Q = (P - 1) // 2
    G = 4
    H = pow(int.from_bytes(hashlib.sha256(b"SentinelPay-v4.2-H").digest(), "big"), 2, P)
    BITS = 32

    @classmethod
    def _challenge(cls, values: list[int], public_price: int, commitment: int) -> int:
        encoded = "|".join(str(value) for value in [public_price, commitment, *values])
        return int.from_bytes(hashlib.sha256(encoded.encode()).digest(), "big") % cls.Q

    @classmethod
    def prove(cls, budget: int, price: int) -> dict:
        if budget < price:
            raise ValueError("Private budget is insufficient")
        delta = budget - price
        if delta >= 2**cls.BITS:
            raise ValueError("Budget difference exceeds circuit range")
        started = time.perf_counter()
        r_budget = secrets.randbelow(cls.Q)
        commitment = pow(cls.G, budget, cls.P) * pow(cls.H, r_budget, cls.P) % cls.P
        bit_values = [(delta >> index) & 1 for index in range(cls.BITS)]
        randomness = [secrets.randbelow(cls.Q) for _ in range(cls.BITS - 1)]
        weighted = sum((1 << index) * value for index, value in enumerate(randomness))
        inverse_weight = pow(1 << (cls.BITS - 1), -1, cls.Q)
        randomness.append((r_budget - weighted) * inverse_weight % cls.Q)
        bit_proofs = []
        for index, (bit, blind) in enumerate(zip(bit_values, randomness, strict=True)):
            bit_commitment = pow(cls.G, bit, cls.P) * pow(cls.H, blind, cls.P) % cls.P
            y = [bit_commitment, bit_commitment * pow(cls.G, -1, cls.P) % cls.P]
            false_branch, true_branch = 1 - bit, bit
            fake_e, fake_z, witness = (
                secrets.randbelow(cls.Q),
                secrets.randbelow(cls.Q),
                secrets.randbelow(cls.Q),
            )
            announcements = [0, 0]
            announcements[false_branch] = (
                pow(cls.H, fake_z, cls.P)
                * pow(pow(y[false_branch], fake_e, cls.P), -1, cls.P)
                % cls.P
            )
            announcements[true_branch] = pow(cls.H, witness, cls.P)
            challenge = cls._challenge(
                [index, bit_commitment, *announcements], price, commitment
            )
            challenges = [0, 0]
            responses = [0, 0]
            challenges[false_branch] = fake_e
            responses[false_branch] = fake_z
            challenges[true_branch] = (challenge - fake_e) % cls.Q
            responses[true_branch] = (
                witness + challenges[true_branch] * blind
            ) % cls.Q
            bit_proofs.append(
                {
                    "commitment": str(bit_commitment),
                    "announcements": [str(value) for value in announcements],
                    "challenges": [str(value) for value in challenges],
                    "responses": [str(value) for value in responses],
                }
            )
        return {
            "statement": "PrivateBudget >= PublicPrice",
            "bits": cls.BITS,
            "budget_commitment": str(commitment),
            "bit_proofs": bit_proofs,
            "generation_ms": int((time.perf_counter() - started) * 1000),
            "security_note": "UNAUDITED_DEMO_RANGE_PROOF_NOT_FULL_POLICY_ZK",
        }

    @classmethod
    def verify(cls, price: int, commitment_text: str, proof: dict) -> dict:
        started = time.perf_counter()
        try:
            commitment = int(commitment_text)
            bits = proof["bit_proofs"]
            if len(bits) != cls.BITS or proof.get("bits") != cls.BITS:
                raise ValueError("Unexpected circuit size")
            product = 1
            for index, item in enumerate(bits):
                bit_commitment = int(item["commitment"])
                announcements = [int(value) for value in item["announcements"]]
                challenges = [int(value) for value in item["challenges"]]
                responses = [int(value) for value in item["responses"]]
                challenge = cls._challenge(
                    [index, bit_commitment, *announcements], price, commitment
                )
                if sum(challenges) % cls.Q != challenge:
                    raise ValueError("Fiat-Shamir challenge mismatch")
                ys = [
                    bit_commitment,
                    bit_commitment * pow(cls.G, -1, cls.P) % cls.P,
                ]
                for branch in (0, 1):
                    left = pow(cls.H, responses[branch], cls.P)
                    right = (
                        announcements[branch]
                        * pow(ys[branch], challenges[branch], cls.P)
                        % cls.P
                    )
                    if left != right:
                        raise ValueError("Invalid bit proof")
                product = product * pow(bit_commitment, 1 << index, cls.P) % cls.P
            delta_commitment = commitment * pow(pow(cls.G, price, cls.P), -1, cls.P) % cls.P
            valid = product == delta_commitment
        except (KeyError, TypeError, ValueError):
            valid = False
        return {
            "verified": valid,
            "verification_ms": int((time.perf_counter() - started) * 1000),
            "statement": "PrivateBudget >= PublicPrice",
        }


class MultiVerifierService:
    @staticmethod
    def canonical(attestation) -> bytes:
        value = {
            "verifier_id": attestation.verifier_id,
            "decision": attestation.decision,
            "payload_hash": attestation.payload_hash,
            "issued_at": attestation.issued_at.astimezone(UTC).isoformat(),
            "expires_at": attestation.expires_at.astimezone(UTC).isoformat(),
        }
        return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()

    def evaluate(self, request: MultiVerifierRequest) -> dict:
        now = datetime.now(UTC)
        expected = set(request.expected_verifiers)
        verified, denied = set(), set()
        for attestation in request.attestations:
            if (
                attestation.verifier_id not in expected
                or attestation.payload_hash != request.payload_hash
                or attestation.expires_at.astimezone(UTC) <= now
            ):
                continue
            try:
                key = Ed25519PublicKey.from_public_bytes(
                    base64.b64decode(attestation.public_key)
                )
                key.verify(
                    base64.b64decode(attestation.signature), self.canonical(attestation)
                )
            except (ValueError, InvalidSignature):
                continue
            verified.add(attestation.verifier_id)
            if attestation.decision == "DENY":
                denied.add(attestation.verifier_id)
        approved = len(verified - denied) >= request.required_k and not denied
        return {
            "status": "APPROVED" if approved else "DENIED",
            "verified_approvals": len(verified - denied),
            "verified_denials": len(denied),
            "required_k": request.required_k,
            "security_kernel_still_required": True,
            "fallback": "DENY",
        }


class ProcurementOptimizer:
    def optimize(self, request: ProcurementOptimizeRequest) -> dict:
        optimizer = Optimize()
        approved = {str(value) for value in request.approved_vendor_ids}
        quantities = [Int(f"allocation_{index}") for index in range(len(request.quotes))]
        costs = []
        objectives = []
        now = datetime.now(UTC)
        for quantity, quote in zip(quantities, request.quotes, strict=True):
            allowed = (
                str(quote.merchant_id) in approved
                and quote.delivery_at.astimezone(UTC) <= request.delivery_deadline.astimezone(UTC)
            )
            optimizer.add(quantity >= 0, quantity <= quote.available_quantity)
            optimizer.add(
                quantity == 0
                if not allowed
                else Or(quantity == 0, quantity >= quote.merchant_minimum_quantity)
            )
            cost = quantity * quote.unit_price_minor
            delivery_days = max(
                0, int((quote.delivery_at.astimezone(UTC) - now).total_seconds() / 86400)
            )
            risk_penalty = int(request.lambda_vendor_risk * quote.vendor_risk_basis_points)
            delivery_penalty = int(request.lambda_delivery * delivery_days * 100)
            costs.append(cost)
            objectives.append(cost + quantity * (risk_penalty + delivery_penalty))
        optimizer.add(Sum(quantities) >= request.required_quantity)
        optimizer.add(Sum(costs) <= request.max_budget_minor)
        optimizer.minimize(Sum(objectives))
        if optimizer.check() != sat:
            return {
                "status": "FALLBACK",
                "reason": "NO_FEASIBLE_ALLOCATION",
                "allocations": [],
                "payment_created": False,
            }
        model = optimizer.model()
        allocations, total_cost, filled = [], 0, 0
        for quantity, quote in zip(quantities, request.quotes, strict=True):
            allocated = model.eval(quantity).as_long()
            if allocated:
                cost = allocated * quote.unit_price_minor
                total_cost += cost
                filled += allocated
                allocations.append(
                    {
                        "quote_id": str(quote.quote_id),
                        "merchant_id": str(quote.merchant_id),
                        "quantity": allocated,
                        "cost_minor": cost,
                    }
                )
        return {
            "status": "SUCCESS",
            "allocations": allocations,
            "metrics": {
                "cost_minor": total_cost,
                "fill_rate": filled / request.required_quantity,
                "deadline_compliance": 1.0,
                "supplier_allocation_quality": request.required_quantity / max(filled, 1),
            },
            "solver": "Z3_OPTIMIZE",
            "payment_created": False,
            "security_kernel_still_required": True,
        }


@dataclass(frozen=True)
class SimulationOutcome:
    reward: float
    agreement: bool
    rounds: int


class NegotiationSimulator:
    @staticmethod
    def _episode(rng: random.Random, strategy: str) -> SimulationOutcome:
        buyer_ceiling = rng.randint(18_500, 25_000)
        seller_floor = rng.randint(17_000, 23_000)
        if seller_floor > buyer_ceiling:
            return SimulationOutcome(-100, False, 1)
        rounds = {"FAST_CLOSE": 1, "BALANCED": 2, "AGGRESSIVE": 4}[strategy]
        target = {
            "FAST_CLOSE": buyer_ceiling,
            "BALANCED": (buyer_ceiling + seller_floor) // 2,
            "AGGRESSIVE": seller_floor,
        }[strategy]
        failure_probability = {"FAST_CLOSE": 0.02, "BALANCED": 0.08, "AGGRESSIVE": 0.25}[
            strategy
        ]
        agreement = rng.random() >= failure_probability
        reward = buyer_ceiling - target - rounds * 10 - (200 if not agreement else 0)
        return SimulationOutcome(reward, agreement, rounds)

    def compare(self, seed: int, episodes: int, candidate: str) -> dict:
        baseline_rng, candidate_rng = random.Random(seed), random.Random(seed)
        baseline = [self._episode(baseline_rng, "FAST_CLOSE") for _ in range(episodes)]
        treatment = [self._episode(candidate_rng, candidate) for _ in range(episodes)]

        def metrics(rows: list[SimulationOutcome]) -> dict:
            return {
                "average_reward": sum(row.reward for row in rows) / len(rows),
                "agreement_rate": sum(row.agreement for row in rows) / len(rows),
                "average_rounds": sum(row.rounds for row in rows) / len(rows),
            }

        baseline_metrics, candidate_metrics = metrics(baseline), metrics(treatment)
        return {
            "status": "RESEARCH_ONLY",
            "seed": seed,
            "episodes": episodes,
            "baseline": {"strategy": "FAST_CLOSE", **baseline_metrics},
            "candidate": {"strategy": candidate, **candidate_metrics},
            "reward_lift": candidate_metrics["average_reward"]
            - baseline_metrics["average_reward"],
            "core_transaction_path": False,
            "provenance": "SIMULATED",
        }
