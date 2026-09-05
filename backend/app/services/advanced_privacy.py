import hashlib
import json
import os
import secrets
import subprocess
import tempfile
import time
from collections import Counter
from pathlib import Path
from typing import Any, ClassVar

import networkx as nx
import pandas as pd
from diffprivlib.tools import mean as dp_mean
from diffprivlib.tools import sum as dp_sum
from phe import paillier
from py_ecc.bls import G2ProofOfPossession as Bls

from app.schemas.advanced import (
    BlsApprovalRequest,
    BlsSignerInput,
    CausalAnalysisRequest,
    DpAggregateRequest,
    HomomorphicAggregateRequest,
    ProvenanceGraphRequest,
)


class CausalAnalysisService:
    """DoWhy backdoor analysis for campaign aggregates with explicit assumptions."""

    @staticmethod
    def analyze(body: CausalAnalysisRequest) -> dict:
        from dowhy import CausalModel

        frame = pd.DataFrame([item.model_dump() for item in body.observations])
        if frame["treatment"].nunique() != 2:
            raise ValueError("Both CONTROL and TREATMENT observations are required")
        model = CausalModel(
            data=frame,
            treatment="treatment",
            outcome="outcome",
            common_causes=["prior_sessions", "inventory_pressure"],
        )
        estimand = model.identify_effect(proceed_when_unidentifiable=False)
        estimate = model.estimate_effect(
            estimand,
            method_name="backdoor.linear_regression",
            test_significance=True,
        )
        random_refutation = model.refute_estimate(
            estimand,
            estimate,
            method_name="random_common_cause",
            random_seed=42,
        )
        placebo_refutation = model.refute_estimate(
            estimand,
            estimate,
            method_name="placebo_treatment_refuter",
            placebo_type="permute",
            num_simulations=20,
            random_seed=42,
        )
        treatment = frame.loc[frame.treatment == 1, "outcome"].mean()
        control = frame.loc[frame.treatment == 0, "outcome"].mean()
        return {
            "method": "DoWhy backdoor.linear_regression",
            "treatment": "campaign_assignment",
            "outcome": "merchant_outcome",
            "common_causes": ["prior_sessions", "inventory_pressure"],
            "causal_graph": "prior_sessions -> treatment,outcome; inventory_pressure -> treatment,outcome; treatment -> outcome",
            "estimand": str(estimand),
            "estimate": float(estimate.value),
            "simple_control_treatment_difference": float(treatment - control),
            "refutations": {
                "random_common_cause": str(random_refutation),
                "placebo_treatment": str(placebo_refutation),
            },
            "assumptions": [
                "conditional exchangeability given declared common causes",
                "positivity",
                "stable treatment and no interference",
            ],
            "causality_claim": "CONDITIONAL_ON_DECLARED_ASSUMPTIONS",
        }


class Groth16BudgetProofService:
    """Circom/snarkjs proof for PrivateBudget >= PublicPrice with ephemeral witness input."""

    ROOT = Path(__file__).resolve().parents[2] / "zk"
    WASM = ROOT / "budget_sufficiency_js" / "budget_sufficiency.wasm"
    ZKEY = ROOT / "build" / "budget_sufficiency_final.zkey"
    VERIFICATION_KEY = ROOT / "build" / "verification_key.json"

    @classmethod
    def available(cls) -> bool:
        return all(path.exists() for path in (cls.WASM, cls.ZKEY, cls.VERIFICATION_KEY))

    CLI = ROOT / "node_modules" / "snarkjs" / "cli.js"

    @classmethod
    def _cmd(cls) -> list[str]:
        if cls.CLI.exists():
            return ["node", str(cls.CLI)]
        npx = "npx.cmd" if os.name == "nt" else "npx"
        return [npx, "-y", "snarkjs"]

    @classmethod
    def prove(cls, private_budget_minor: int, public_price_minor: int) -> dict:
        if not cls.available():
            raise RuntimeError("Groth16 proving artifacts are unavailable")
        if private_budget_minor < public_price_minor:
            raise ValueError("Private budget is insufficient")
        if max(private_budget_minor, public_price_minor) >= 2**32:
            raise ValueError("Budget or price exceeds 32-bit circuit range")
        started = time.perf_counter()
        with tempfile.TemporaryDirectory(prefix="sentinelpay-zk-") as directory:
            temporary = Path(directory)
            input_path = temporary / "input.json"
            proof_path = temporary / "proof.json"
            public_path = temporary / "public.json"
            input_path.write_text(
                json.dumps(
                    {
                        "privateBudget": private_budget_minor,
                        "publicPrice": public_price_minor,
                    }
                ),
                encoding="utf-8",
            )
            cmd = cls._cmd() + [
                "groth16",
                "fullprove",
                str(input_path),
                str(cls.WASM),
                str(cls.ZKEY),
                str(proof_path),
                str(public_path),
            ]
            completed = subprocess.run(
                cmd,
                cwd=cls.ROOT,
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
            )
            if completed.returncode != 0:
                raise RuntimeError(f"Groth16 proof generation failed: {completed.stderr}")
            proof = json.loads(proof_path.read_text(encoding="utf-8"))
            public_signals = json.loads(public_path.read_text(encoding="utf-8"))
        result = {
            "scheme": "GROTH16_BN128",
            "statement": "PrivateBudget >= PublicPrice",
            "proof": proof,
            "public_signals": public_signals,
            "public_price_minor": public_price_minor,
            "generation_ms": int((time.perf_counter() - started) * 1000),
            "circuit_sha256": hashlib.sha256(cls.WASM.read_bytes()).hexdigest(),
            "verification_key_sha256": hashlib.sha256(
                cls.VERIFICATION_KEY.read_bytes()
            ).hexdigest(),
            "private_budget_persisted": False,
            "setup": "CONTROLLED_TEST_MODE_CEREMONY_NOT_PRODUCTION_MPC",
        }
        result["verified"] = cls.verify(result)
        return result

    @classmethod
    def verify(cls, result: dict[str, Any]) -> bool:
        if not cls.available():
            return False
        try:
            with tempfile.TemporaryDirectory(prefix="sentinelpay-zk-verify-") as directory:
                temporary = Path(directory)
                proof_path = temporary / "proof.json"
                public_path = temporary / "public.json"
                proof_path.write_text(json.dumps(result["proof"]), encoding="utf-8")
                public_path.write_text(json.dumps(result["public_signals"]), encoding="utf-8")
                cmd = cls._cmd() + [
                    "groth16",
                    "verify",
                    str(cls.VERIFICATION_KEY),
                    str(public_path),
                    str(proof_path),
                ]
                completed = subprocess.run(
                    cmd,
                    cwd=cls.ROOT,
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False,
                )
                return completed.returncode == 0 and "OK!" in completed.stdout
        except (KeyError, OSError, subprocess.SubprocessError, TypeError, ValueError):
            return False


class DifferentialPrivacyService:
    """DP is restricted to bounded aggregate analytics, never financial source-of-truth rows."""

    @staticmethod
    def aggregate(body: DpAggregateRequest) -> dict:
        if body.lower >= body.upper:
            raise ValueError("DP lower bound must be below upper bound")
        values = [min(body.upper, max(body.lower, value)) for value in body.values]
        if body.statistic == "MEAN":
            private_value = float(
                dp_mean(values, epsilon=body.epsilon, bounds=(body.lower, body.upper), random_state=42)
            )
            true_value = sum(values) / len(values)
        elif body.statistic == "SUM":
            private_value = float(
                dp_sum(values, epsilon=body.epsilon, bounds=(body.lower, body.upper), random_state=42)
            )
            true_value = sum(values)
        else:
            bounded_ones = [1.0] * len(values)
            private_value = float(
                dp_sum(bounded_ones, epsilon=body.epsilon, bounds=(0, 1), random_state=42)
            )
            true_value = float(len(values))
        return {
            "statistic": body.statistic,
            "value": private_value,
            "epsilon": body.epsilon,
            "bounds": [body.lower, body.upper],
            "records": len(values),
            "absolute_noise": abs(private_value - true_value),
            "scope": "AGGREGATE_ANALYTICS_ONLY",
            "ledger_mutated": False,
        }


class ProvenanceGraphService:
    @staticmethod
    def analyze(body: ProvenanceGraphRequest) -> dict:
        graph = nx.DiGraph()
        for node in body.nodes:
            graph.add_node(node.id, kind=node.kind, **node.attributes)
        for edge in body.edges:
            if edge.source not in graph or edge.target not in graph:
                raise ValueError("Every provenance edge must reference declared nodes")
            graph.add_edge(edge.source, edge.target, relation=edge.relation)
        if not nx.is_directed_acyclic_graph(graph):
            raise ValueError("Financial provenance graph must be acyclic")
        paths: list[list[str]] = []
        if body.source_id and body.target_id:
            if body.source_id not in graph or body.target_id not in graph:
                raise ValueError("Requested provenance path node does not exist")
            paths = list(nx.all_simple_paths(graph, body.source_id, body.target_id))
        trust_counts = Counter(
            str(attributes.get("trust_class", "UNSPECIFIED"))
            for _, attributes in graph.nodes(data=True)
        )
        return {
            "nodes": graph.number_of_nodes(),
            "edges": graph.number_of_edges(),
            "acyclic": True,
            "topological_order": list(nx.topological_sort(graph)),
            "paths": paths,
            "trust_class_counts": dict(trust_counts),
            "database_source_of_truth": True,
            "representation": "NETWORKX_ANALYTICAL_VIEW",
        }


class HomomorphicAnalyticsService:
    """Paillier encrypted addition for aggregate arithmetic; comparisons are intentionally excluded."""

    @staticmethod
    def aggregate(body: HomomorphicAggregateRequest) -> dict:
        started = time.perf_counter()
        public_key, private_key = paillier.generate_paillier_keypair(n_length=2048)
        encrypted = [public_key.encrypt(value) for value in body.values]
        encrypted_sum = sum(encrypted[1:], start=encrypted[0])
        decrypted_sum = int(private_key.decrypt(encrypted_sum))
        return {
            "scheme": "PAILLIER_2048",
            "operation": "ENCRYPTED_SUM",
            "records": len(body.values),
            "decrypted_sum": decrypted_sum,
            "verified": decrypted_sum == sum(body.values),
            "ciphertext_fingerprint": hashlib.sha256(
                str(encrypted_sum.ciphertext()).encode()
            ).hexdigest(),
            "elapsed_ms": int((time.perf_counter() - started) * 1000),
            "supports_comparison": False,
            "financial_ledger_mutated": False,
        }


class BlsMultiVerifierService:
    ROLES: ClassVar[set[str]] = {"MANDATE", "POLICY", "RISK"}

    @staticmethod
    def key_pair() -> tuple[int, bytes]:
        private_key = Bls.KeyGen(secrets.token_bytes(32))
        return private_key, Bls.SkToPk(private_key)

    @classmethod
    def approve(cls, body: BlsApprovalRequest) -> dict:
        unique_roles = {item.verifier_id for item in body.signers}
        if len(unique_roles) != len(body.signers) or not unique_roles <= cls.ROLES:
            raise ValueError("BLS verifier roles must be distinct and recognized")
        if len(unique_roles) < body.required_k:
            raise ValueError("Insufficient independent verifier roles")
        message = bytes.fromhex(body.payload_hash)
        public_keys = [Bls.SkToPk(item.private_key) for item in body.signers]
        signatures = [Bls.Sign(item.private_key, message) for item in body.signers]
        individual = [Bls.Verify(pk, message, signature) for pk, signature in zip(public_keys, signatures, strict=True)]
        aggregate = Bls.Aggregate(signatures)
        aggregate_valid = Bls.FastAggregateVerify(public_keys, message, aggregate)
        approved = aggregate_valid and sum(individual) >= body.required_k
        return {
            "status": "APPROVED" if approved else "DENIED",
            "scheme": "BLS12-381_G2_PROOF_OF_POSSESSION",
            "required_k": body.required_k,
            "independent_verifiers": [item.verifier_id for item in body.signers],
            "individual_valid": individual,
            "aggregate_valid": aggregate_valid,
            "aggregate_signature": aggregate.hex(),
            "public_keys": [key.hex() for key in public_keys],
            "payload_hash": body.payload_hash,
            "security_kernel_still_required": True,
        }

    @classmethod
    def approve_with_server_secret(cls, payload_hash: str, server_secret: str) -> dict:
        result = cls.approve_with_role_secrets(
            payload_hash,
            {
                role: f"SentinelPay:development:{role}:{server_secret}"
                for role in sorted(cls.ROLES)
            },
        )
        result["key_source"] = "DEVELOPMENT_DERIVED_ROLE_KEYS"
        return result

    @classmethod
    def approve_with_role_secrets(
        cls, payload_hash: str, role_secrets: dict[str, str]
    ) -> dict:
        if set(role_secrets) != cls.ROLES or any(not value for value in role_secrets.values()):
            raise ValueError("All three independent BLS role secrets are required")
        signers = [
            BlsSignerInput(
                verifier_id=role,
                private_key=Bls.KeyGen(hashlib.sha256(role_secrets[role].encode()).digest()),
            )
            for role in sorted(cls.ROLES)
        ]
        result = cls.approve(
            BlsApprovalRequest(payload_hash=payload_hash, signers=signers, required_k=2)
        )
        result["key_source"] = "INDEPENDENT_DEPLOYMENT_ROLE_SECRETS"
        return result


class WesolowskiVdfService:
    """Wesolowski proof of repeated squaring in an RSA group for sealed-bid reveal timing."""

    # An unknown-order modulus generated for SentinelPay's controlled demonstration parameters.
    N = int(
        "29500761190043976954808793687252760338498732996362519575587162393001693876839599892275349990744028831287798137621630697556872266967589432516689307612599486077562508537929111101757948132931281296748855037321729835789896371847343250481858518514029969027439191967690931562010740731397461858867141381928301198435687780344014702185810136672866333516498329516082386032399919884754444065258446408760078303782556305991287072380888624216123429577229407590928100114435234781980900047726332562415086020855702737825902922209710489650279428864441043458819587277984889528166404601819955524939958910794248481300102489810809901576529"
    )

    @staticmethod
    def _is_probable_prime(value: int) -> bool:
        if value < 2:
            return False
        for prime in (2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37):
            if value % prime == 0:
                return value == prime
        exponent, odd = 0, value - 1
        while odd % 2 == 0:
            exponent += 1
            odd //= 2
        for base in (2, 3, 5, 7, 11, 13, 17):
            x = pow(base, odd, value)
            if x in (1, value - 1):
                continue
            for _ in range(exponent - 1):
                x = pow(x, 2, value)
                if x == value - 1:
                    break
            else:
                return False
        return True

    @classmethod
    def _challenge_prime(cls, x: int, y: int, iterations: int) -> int:
        candidate = int.from_bytes(
            hashlib.sha256(f"{x}|{y}|{iterations}".encode()).digest()[:16], "big"
        ) | 1
        while not cls._is_probable_prime(candidate):
            candidate += 2
        return candidate

    @classmethod
    def evaluate(cls, challenge: str, iterations: int) -> dict:
        started = time.perf_counter()
        x = int.from_bytes(hashlib.sha256(challenge.encode()).digest(), "big") % cls.N
        x = max(2, x)
        y = x
        for _ in range(iterations):
            y = pow(y, 2, cls.N)
        prime = cls._challenge_prime(x, y, iterations)
        quotient, remainder = divmod(1 << iterations, prime)
        proof = pow(x, quotient, cls.N)
        elapsed = int((time.perf_counter() - started) * 1000)
        return {
            "scheme": "WESOLOWSKI_RSA_GROUP",
            "setup_id": hashlib.sha256(str(cls.N).encode()).hexdigest(),
            "purpose": "SEALED_BID_REVEAL_DELAY",
            "attack_addressed": "PREMATURE_REVEAL_AND_TIMING_MANIPULATION",
            "iterations": iterations,
            "x": str(x),
            "y": str(y),
            "proof": str(proof),
            "challenge_prime": str(prime),
            "remainder": str(remainder),
            "evaluation_ms": elapsed,
            "verified": cls.verify(x, y, proof, prime, remainder),
        }

    @classmethod
    def verify(cls, x: int, y: int, proof: int, prime: int, remainder: int) -> bool:
        return pow(proof, prime, cls.N) * pow(x, remainder, cls.N) % cls.N == y

    @classmethod
    def verify_result(cls, result: dict[str, Any]) -> bool:
        try:
            return cls.verify(
                int(result["x"]),
                int(result["y"]),
                int(result["proof"]),
                int(result["challenge_prime"]),
                int(result["remainder"]),
            )
        except (KeyError, TypeError, ValueError):
            return False
