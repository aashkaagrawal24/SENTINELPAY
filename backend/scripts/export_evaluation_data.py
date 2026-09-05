import csv
import json
import time
from pathlib import Path

from app.schemas.advanced import NegotiabilityFeatures
from app.services.advanced_intelligence import get_negotiability_model
from app.services.advanced_privacy import Groth16BudgetProofService, WesolowskiVdfService
from app.services.judge_service import JudgeService


def export_negotiability_dataset(output_dir: Path):
    """Exports a deterministic negotiability training dataset to CSV."""
    model = get_negotiability_model()
    # The get_negotiability_model() already loads training data internally for the model,
    # but we can synthesize a representative set based on the bounds.
    # For export, we'll generate 500 rows that span the feature space.
    
    rows = []
    platforms = ["AMAZON", "FLIPKART", "OLX", "INDIAMART"]
    seller_types = ["MERCHANT", "INDIVIDUAL"]
    categories = ["ELECTRONICS", "VEHICLES", "REAL_ESTATE"]
    
    for p in platforms:
        for s in seller_types:
            for c in categories:
                for age in [1, 30, 90]:
                    for rfq in [True, False]:
                        for neg in [True, False]:
                            f = NegotiabilityFeatures(
                                platform=p,
                                seller_type=s,
                                category=c,
                                listing_age_days=age,
                                explicit_negotiable=neg,
                                rfq_supported=rfq,
                                quantity=10 if rfq else 1,
                                historical_price_edits=2 if age > 30 else 0,
                                price_roundness=1.0 if s == "INDIVIDUAL" else 0.5,
                                merchant_negotiation_enabled=s == "MERCHANT",
                            )
                            score = model.predict(f)["negotiability_score"]
                            rows.append({
                                "platform": p,
                                "seller_type": s,
                                "category": c,
                                "listing_age_days": age,
                                "explicit_negotiable": int(neg),
                                "rfq_supported": int(rfq),
                                "score": round(score, 4)
                            })
                            
    csv_path = output_dir / "negotiability_dataset.csv"
    with csv_path.open("w", newline="") as csv_f:
        writer = csv.DictWriter(csv_f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    print(f"Exported {len(rows)} negotiability rows to {csv_path}")
    
    metrics_path = output_dir / "negotiability_metrics.json"
    
    # Use a dummy feature to get metrics
    dummy_f = NegotiabilityFeatures(
        platform="AMAZON",
        seller_type="MERCHANT",
        category="ELECTRONICS",
        listing_age_days=1,
        explicit_negotiable=True,
        rfq_supported=False,
        quantity=1,
        historical_price_edits=0,
        price_roundness=0.5,
        merchant_negotiation_enabled=True,
    )
    metrics_path.write_text(json.dumps(model.predict(dummy_f)["metrics"], indent=2))
    print(f"Exported metrics to {metrics_path}")


def run_crypto_benchmarks(output_dir: Path):
    """Runs and exports cryptographic benchmarks."""
    results = {}
    
    # ZK Budget Proof
    t0 = time.perf_counter()
    proof = Groth16BudgetProofService.prove(2_500_000, 1_999_900)
    t1 = time.perf_counter()
    Groth16BudgetProofService.verify(proof)
    t2 = time.perf_counter()
    
    results["zk_groth16"] = {
        "prove_ms": round((t1 - t0) * 1000, 2),
        "verify_ms": round((t2 - t1) * 1000, 2),
        "proof_bytes": len(json.dumps(proof).encode())
    }
    
    # VDF Reveal
    t0 = time.perf_counter()
    vdf = WesolowskiVdfService.evaluate("sealed-bid-commitment", 2000)
    t1 = time.perf_counter()
    WesolowskiVdfService.verify_result(vdf)
    t2 = time.perf_counter()
    
    results["vdf_wesolowski_2048"] = {
        "evaluate_ms": round((t1 - t0) * 1000, 2),
        "verify_ms": round((t2 - t1) * 1000, 2)
    }
    
    bench_path = output_dir / "crypto_benchmarks.json"
    bench_path.write_text(json.dumps(results, indent=2))
    print(f"Exported crypto benchmarks to {bench_path}")


if __name__ == "__main__":
    out = Path(__file__).parent.parent / "data"
    out.mkdir(exist_ok=True)
    export_negotiability_dataset(out)
    run_crypto_benchmarks(out)
