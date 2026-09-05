import math
import random
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import ClassVar

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, precision_recall_fscore_support, roc_auc_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from app.schemas.advanced import (
    ExternalOfferInput,
    LinUcbState,
    NegotiabilityFeatures,
    RacRequest,
)


class PlatformMode(StrEnum):
    NEGOTIATION_MARKETPLACE = "NEGOTIATION_MARKETPLACE"
    SEMI_NEGOTIABLE = "SEMI_NEGOTIABLE"
    FIXED_SCOUT = "FIXED_SCOUT"


@dataclass(frozen=True)
class PlatformDefinition:
    key: str
    name: str
    mode: PlatformMode
    authentication: str
    search: bool
    live_price: bool
    inventory: bool
    negotiation: bool
    offers: bool
    checkout: bool
    razorpay_execution: bool
    handoff: bool
    data_source: str


class PlatformRegistry:
    _NAMES: ClassVar[tuple[tuple[str, PlatformMode, bool], ...]] = (
        ("OLX", PlatformMode.NEGOTIATION_MARKETPLACE, True),
        ("QUIKR", PlatformMode.NEGOTIATION_MARKETPLACE, True),
        ("FACEBOOK_MARKETPLACE", PlatformMode.NEGOTIATION_MARKETPLACE, True),
        ("INDIAMART", PlatformMode.NEGOTIATION_MARKETPLACE, True),
        ("TRADEINDIA", PlatformMode.NEGOTIATION_MARKETPLACE, True),
        ("LOCAL_CLASSIFIEDS", PlatformMode.NEGOTIATION_MARKETPLACE, True),
        ("MEESHO", PlatformMode.SEMI_NEGOTIABLE, False),
        ("SHOPCLUES", PlatformMode.SEMI_NEGOTIABLE, False),
        ("SNAPDEAL", PlatformMode.SEMI_NEGOTIABLE, False),
        ("JIOMART", PlatformMode.SEMI_NEGOTIABLE, False),
        ("AMAZON", PlatformMode.FIXED_SCOUT, False),
        ("FLIPKART", PlatformMode.FIXED_SCOUT, False),
        ("MYNTRA", PlatformMode.FIXED_SCOUT, False),
        ("NYKAA", PlatformMode.FIXED_SCOUT, False),
        ("TATA_CLIQ", PlatformMode.FIXED_SCOUT, False),
        ("CROMA", PlatformMode.FIXED_SCOUT, False),
        ("RELIANCE_DIGITAL", PlatformMode.FIXED_SCOUT, False),
    )

    @classmethod
    def all(cls) -> list[PlatformDefinition]:
        return [
            PlatformDefinition(
                key=key,
                name=key.replace("_", " ").title(),
                mode=mode,
                authentication="PLATFORM_HANDOFF",
                search=True,
                live_price=False,
                inventory=False,
                negotiation=negotiable,
                offers=True,
                checkout=False,
                razorpay_execution=False,
                handoff=True,
                data_source="CONTROLLED_SNAPSHOT_OR_USER_HANDOFF",
            )
            for key, mode, negotiable in cls._NAMES
        ]

    @classmethod
    def get(cls, key: str) -> PlatformDefinition:
        normalized = key.strip().upper().replace(" ", "_")
        definition = next((item for item in cls.all() if item.key == normalized), None)
        if definition is None:
            raise KeyError(f"Unknown platform: {key}")
        return definition


class ConnectorRateLimiter:
    def __init__(self, minimum_interval_seconds: float = 0.05):
        self.minimum_interval_seconds = minimum_interval_seconds
        self._last_call: dict[str, float] = {}
        self._lock = threading.Lock()

    def wait(self, connector: str) -> None:
        with self._lock:
            now = time.monotonic()
            delay = self.minimum_interval_seconds - (now - self._last_call.get(connector, 0))
            if delay > 0:
                time.sleep(delay)
            self._last_call[connector] = time.monotonic()


class ControlledPlatformConnector:
    """Capability-aware adapter for controlled snapshots; unsupported actions always hand off."""

    def __init__(
        self,
        platform: PlatformDefinition,
        offers: list[ExternalOfferInput],
        fail: bool = False,
    ):
        self.platform = platform
        self.offers = offers
        self.fail = fail

    def search(self, query: str) -> list[ExternalOfferInput]:
        del query
        if self.fail:
            raise RuntimeError(f"{self.platform.key} connector unavailable")
        return self.offers


class ProductIdentityResolver:
    FIELDS: ClassVar[tuple[str, ...]] = (
        "brand",
        "model",
        "variant",
        "capacity",
        "generation",
        "condition",
        "bundle",
        "warranty",
    )

    @staticmethod
    def _tokens(value: str) -> set[str]:
        return {token for token in "".join(c.lower() if c.isalnum() else " " for c in value).split()}

    @classmethod
    def resolve(cls, expected: dict[str, str], offer: ExternalOfferInput) -> dict:
        title_tokens = cls._tokens(offer.title)
        field_scores: dict[str, float] = {}
        contradictions = 0
        for field_name in cls.FIELDS:
            expected_value = expected.get(field_name)
            if not expected_value:
                continue
            expected_tokens = cls._tokens(expected_value)
            overlap = len(expected_tokens & title_tokens) / max(1, len(expected_tokens))
            field_scores[field_name] = overlap
            if field_name in {"brand", "model", "capacity", "generation", "condition"} and overlap == 0:
                contradictions += 1
        score = sum(field_scores.values()) / max(1, len(field_scores))
        if contradictions:
            classification = "NOT_COMPARABLE" if contradictions >= 2 else "POSSIBLE"
        elif score >= 0.95:
            classification = "EXACT"
        elif score >= 0.7:
            classification = "EQUIVALENT"
        elif score >= 0.4:
            classification = "POSSIBLE"
        else:
            classification = "NOT_COMPARABLE"
        return {
            "classification": classification,
            "score": round(score, 6),
            "field_scores": field_scores,
            "contradictions": contradictions,
        }


class UniversalWebScout:
    def __init__(self, rate_limiter: ConnectorRateLimiter | None = None):
        self.rate_limiter = rate_limiter or ConnectorRateLimiter()

    def _search_one(
        self,
        connector: ControlledPlatformConnector,
        query: str,
        expected: dict[str, str],
    ) -> dict:
        started = time.perf_counter()
        self.rate_limiter.wait(connector.platform.key)
        try:
            offers = connector.search(query)
            normalized = []
            for offer in offers:
                identity = ProductIdentityResolver.resolve(expected, offer)
                normalized.append(
                    {
                        **offer.model_dump(mode="json"),
                        "platform": connector.platform.key,
                        "identity": identity,
                        "checkout_capability": "HANDOFF",
                        "handoff_required": True,
                        "provenance": "CONTROLLED_DEMO",
                    }
                )
            return {
                "platform": connector.platform.key,
                "status": "SUCCESS",
                "offers": normalized,
                "latency_ms": int((time.perf_counter() - started) * 1000),
            }
        except Exception as exc:  # noqa: BLE001 - partial connector failure is isolated.
            return {
                "platform": connector.platform.key,
                "status": "HANDOFF",
                "offers": [],
                "reason": type(exc).__name__,
                "latency_ms": int((time.perf_counter() - started) * 1000),
            }

    def search(
        self,
        connectors: list[ControlledPlatformConnector],
        query: str,
        expected: dict[str, str],
        timeout_seconds: float,
    ) -> dict:
        started = time.perf_counter()
        results: list[dict] = []
        with ThreadPoolExecutor(max_workers=min(8, max(1, len(connectors)))) as executor:
            futures = {
                executor.submit(self._search_one, connector, query, expected): connector
                for connector in connectors
            }
            try:
                for future in as_completed(futures, timeout=timeout_seconds):
                    results.append(future.result())
            except TimeoutError:
                pass
            completed = {item["platform"] for item in results}
            for connector in connectors:
                if connector.platform.key not in completed:
                    results.append(
                        {
                            "platform": connector.platform.key,
                            "status": "HANDOFF",
                            "offers": [],
                            "reason": "TIMEOUT",
                        }
                    )
        offers = [offer for result in results for offer in result["offers"]]
        offers.sort(
            key=lambda item: (
                {"EXACT": 3, "EQUIVALENT": 2, "POSSIBLE": 1}.get(
                    item["identity"]["classification"], 0
                ),
                -item["price_minor"],
            ),
            reverse=True,
        )
        return {
            "status": "SUCCESS" if offers else "HANDOFF",
            "connector_results": sorted(results, key=lambda item: item["platform"]),
            "offers": offers,
            "metrics": {
                "registered_connectors": len(PlatformRegistry.all()),
                "queried_connectors": len(connectors),
                "successful_connectors": sum(item["status"] == "SUCCESS" for item in results),
                "partial_failures": sum(item["status"] != "SUCCESS" for item in results),
                "latency_ms": int((time.perf_counter() - started) * 1000),
            },
            "payment_created": False,
        }


class RiskAdjustedCostService:
    @staticmethod
    def calculate(body: RacRequest) -> dict:
        components = body.model_dump(mode="json")
        values = {name: int(value["amount_minor"]) for name, value in components.items()}
        total = (
            values["price"]
            + values["shipping"]
            - values["verified_discount"]
            - values["confirmed_cashback"]
            + values["condition_penalty"]
            + values["warranty_penalty"]
            + values["seller_risk_penalty"]
            + values["delivery_penalty"]
        )
        return {
            "risk_adjusted_acquisition_cost_minor": total,
            "currency": "INR",
            "formula": "Price + Shipping - VerifiedDiscount - ConfirmedCashback + ConditionPenalty + WarrantyPenalty + SellerRiskPenalty + DeliveryPenalty",
            "components": components,
        }


class NegotiabilityModel:
    CATEGORICAL: ClassVar[list[str]] = ["platform", "seller_type", "category"]
    NUMERIC: ClassVar[list[str]] = [
        "listing_age_days",
        "explicit_negotiable",
        "rfq_supported",
        "quantity",
        "historical_price_edits",
        "price_roundness",
        "merchant_negotiation_enabled",
    ]

    def __init__(self):
        categorical = OneHotEncoder(handle_unknown="ignore")
        numeric = Pipeline([("scale", StandardScaler())])
        self.pipeline = Pipeline(
            [
                (
                    "features",
                    ColumnTransformer(
                        [("categorical", categorical, self.CATEGORICAL), ("numeric", numeric, self.NUMERIC)]
                    ),
                ),
                ("classifier", LogisticRegression(random_state=42, max_iter=1_000)),
            ]
        )
        self.metrics: dict[str, float] = {}
        artifact = Path(__file__).resolve().parents[2] / "artifacts" / "negotiability-v1.joblib"
        if artifact.exists():
            saved = joblib.load(artifact)
            self.pipeline = saved["pipeline"]
            self.metrics = saved["metrics"]
        else:
            self._train()

    @staticmethod
    def _dataset() -> tuple[list[dict], list[int]]:
        rng = random.Random(4207)
        rows, labels = [], []
        platforms = ["OLX", "INDIAMART", "AMAZON", "FLIPKART", "LOCAL_CLASSIFIEDS"]
        for index in range(240):
            platform = platforms[index % len(platforms)]
            explicit = platform in {"OLX", "LOCAL_CLASSIFIEDS"} and index % 3 != 0
            rfq = platform == "INDIAMART"
            merchant = index % 4 == 0
            age = rng.randint(0, 180)
            quantity = 1 if index % 5 else rng.randint(5, 100)
            edits = rng.randint(0, 8)
            probability = (
                0.08
                + 0.48 * explicit
                + 0.35 * rfq
                + 0.24 * merchant
                + 0.12 * (age > 45)
                + 0.16 * (quantity > 4)
                + 0.08 * (edits > 2)
            )
            rows.append(
                {
                    "platform": platform,
                    "seller_type": "MERCHANT" if merchant else "INDIVIDUAL",
                    "category": "ELECTRONICS" if index % 2 else "GENERAL",
                    "listing_age_days": age,
                    "explicit_negotiable": int(explicit),
                    "rfq_supported": int(rfq),
                    "quantity": quantity,
                    "historical_price_edits": edits,
                    "price_roundness": 1.0 if index % 3 == 0 else 0.2,
                    "merchant_negotiation_enabled": int(merchant),
                }
            )
            labels.append(int(rng.random() < min(probability, 0.96)))
        return rows, labels

    def _train(self) -> None:
        rows, labels = self._dataset()
        split = 180
        self.pipeline.fit(pd.DataFrame(rows[:split]), labels[:split])
        probabilities = self.pipeline.predict_proba(pd.DataFrame(rows[split:]))[:, 1]
        predictions = (probabilities >= 0.5).astype(int)
        precision, recall, f1, _ = precision_recall_fscore_support(
            labels[split:], predictions, average="binary", zero_division=0
        )
        self.metrics = {
            "precision": round(float(precision), 6),
            "recall": round(float(recall), 6),
            "f1": round(float(f1), 6),
            "roc_auc": round(float(roc_auc_score(labels[split:], probabilities)), 6),
            "brier_score": round(float(brier_score_loss(labels[split:], probabilities)), 6),
            "training_rows": split,
            "evaluation_rows": len(rows) - split,
        }

    def predict(self, features: NegotiabilityFeatures) -> dict:
        row = features.model_dump()
        probability = float(self.pipeline.predict_proba(pd.DataFrame([row]))[0, 1])
        return {
            "negotiability_score": round(probability, 6),
            "classification": "NEGOTIABLE" if probability >= 0.5 else "UNLIKELY_NEGOTIABLE",
            "strategy_influence": "NEGOTIATE" if probability >= 0.65 else "DIRECT_OR_HANDOFF",
            "model": "sklearn-logistic-regression-v1",
            "metrics": self.metrics,
            "training_data": "DETERMINISTIC_CONTROLLED_DATASET",
        }


@lru_cache(maxsize=1)
def get_negotiability_model() -> NegotiabilityModel:
    return NegotiabilityModel()


class LinUcbService:
    ACTIONS = ("AGGRESSIVE", "BALANCED", "FAST_CLOSE", "BULK_DISCOUNT", "DEADLINE_BASED")

    @staticmethod
    def _arrays(state: LinUcbState, dimension: int) -> tuple[np.ndarray, np.ndarray]:
        a_matrix = np.asarray(state.a_matrix, dtype=float)
        b_vector = np.asarray(state.b_vector, dtype=float)
        if a_matrix.shape != (dimension, dimension) or b_vector.shape != (dimension,):
            raise ValueError("LinUCB state dimension does not match context")
        return a_matrix, b_vector

    def select(self, context: list[float], alpha: float, states: list[LinUcbState]) -> dict:
        if not states:
            raise ValueError("At least one LinUCB action state is required")
        x = np.asarray(context, dtype=float)
        scores: dict[str, float] = {}
        for state in states:
            a_matrix, b_vector = self._arrays(state, len(context))
            inverse = np.linalg.inv(a_matrix)
            theta = inverse @ b_vector
            score = float(theta @ x + alpha * math.sqrt(max(0.0, x @ inverse @ x)))
            scores[state.action] = score
        selected = max(scores, key=scores.get)
        return {
            "action": selected,
            "scores": {key: round(value, 8) for key, value in scores.items()},
            "algorithm": "LinUCB",
            "authority_changes": {},
            "baseline": "BALANCED",
        }

    def update(self, context: list[float], reward: float, state: LinUcbState) -> dict:
        x = np.asarray(context, dtype=float)
        a_matrix, b_vector = self._arrays(state, len(context))
        updated_a = a_matrix + np.outer(x, x)
        updated_b = b_vector + reward * x
        return {
            "action": state.action,
            "a_matrix": updated_a.tolist(),
            "b_vector": updated_b.tolist(),
            "observations": state.observations + 1,
        }


@dataclass
class CfrInfoSet:
    actions: tuple[str, ...]
    regret_sum: np.ndarray = field(init=False)
    strategy_sum: np.ndarray = field(init=False)

    def __post_init__(self) -> None:
        self.regret_sum = np.zeros(len(self.actions), dtype=float)
        self.strategy_sum = np.zeros(len(self.actions), dtype=float)

    def strategy(self, reach_probability: float) -> np.ndarray:
        positive = np.maximum(self.regret_sum, 0)
        strategy = positive / positive.sum() if positive.sum() else np.full(len(self.actions), 1 / len(self.actions))
        self.strategy_sum += reach_probability * strategy
        return strategy

    def average(self) -> dict[str, float]:
        total = self.strategy_sum.sum()
        values = self.strategy_sum / total if total else np.full(len(self.actions), 1 / len(self.actions))
        return dict(zip(self.actions, (round(float(value), 6) for value in values), strict=True))


class CfrBargainingService:
    OFFERS = (50, 65, 80)
    MAX_ROUNDS = 3

    def __init__(self, seed: int = 42):
        self.rng = random.Random(seed)
        self.infosets: dict[str, CfrInfoSet] = {}

    def _node(self, key: str, actions: tuple[str, ...]) -> CfrInfoSet:
        return self.infosets.setdefault(key, CfrInfoSet(actions))

    def _seller(
        self, buyer_value: int, seller_floor: int, round_index: int, offer: int, reach_b: float, reach_s: float
    ) -> float:
        node = self._node(f"S:{seller_floor}:{round_index}:{offer}", ("ACCEPT", "REJECT"))
        strategy = node.strategy(reach_s)
        utilities = np.zeros(2)
        utilities[0] = (buyer_value - offer) - (offer - seller_floor)
        utilities[1] = self._buyer(buyer_value, seller_floor, round_index + 1, reach_b, reach_s * strategy[1])
        utility = float(strategy @ utilities)
        node.regret_sum += reach_b * (utility - utilities)
        return utility

    def _buyer(self, buyer_value: int, seller_floor: int, round_index: int, reach_b: float, reach_s: float) -> float:
        if round_index >= self.MAX_ROUNDS:
            return 0.0
        actions = tuple(str(value) for value in self.OFFERS) + ("EXIT",)
        node = self._node(f"B:{buyer_value}:{round_index}", actions)
        strategy = node.strategy(reach_b)
        utilities = np.zeros(len(actions))
        for index, action in enumerate(actions):
            utilities[index] = 0 if action == "EXIT" else self._seller(
                buyer_value, seller_floor, round_index, int(action), reach_b * strategy[index], reach_s
            )
        utility = float(strategy @ utilities)
        node.regret_sum += reach_s * (utilities - utility)
        return utility

    def train(self, iterations: int) -> dict:
        started = time.perf_counter()
        utility = 0.0
        for _ in range(iterations):
            buyer_value = self.rng.choice((80, 100))
            seller_floor = self.rng.choice((40, 60))
            utility += self._buyer(buyer_value, seller_floor, 0, 1.0, 1.0)
        strategies = {key: node.average() for key, node in sorted(self.infosets.items())}
        nonzero_regrets = sum(int(np.any(node.regret_sum != 0)) for node in self.infosets.values())
        return {
            "algorithm": "COUNTERFACTUAL_REGRET_MINIMIZATION",
            "iterations": iterations,
            "hidden_information": ["buyer_reservation_value", "seller_reservation_price"],
            "rounds": self.MAX_ROUNDS,
            "information_sets": len(self.infosets),
            "information_sets_with_regret_updates": nonzero_regrets,
            "average_game_utility": round(utility / iterations, 6),
            "average_strategies": strategies,
            "elapsed_ms": int((time.perf_counter() - started) * 1000),
            "benchmarks": self._benchmark(),
        }

    @staticmethod
    def _benchmark() -> dict:
        scenarios = [(buyer, seller) for buyer in (80, 100) for seller in (40, 60)]
        static_agreements = sum(65 >= seller and 65 <= buyer for buyer, seller in scenarios)
        rule_agreements = sum(min(buyer, seller + 20) >= seller for buyer, seller in scenarios)
        return {
            "static_bargaining_agreement_rate": static_agreements / len(scenarios),
            "rule_based_agreement_rate": rule_agreements / len(scenarios),
            "bandit_comparison": "LinUCB selects posture; CFR learns information-set strategies",
        }
