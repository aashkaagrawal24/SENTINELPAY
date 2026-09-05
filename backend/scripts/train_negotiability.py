import hashlib
import json
from pathlib import Path

import joblib
import pandas as pd

from app.services.advanced_intelligence import NegotiabilityModel


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    data_dir = root / "data"
    artifact_dir = root / "artifacts"
    data_dir.mkdir(exist_ok=True)
    artifact_dir.mkdir(exist_ok=True)
    rows, labels = NegotiabilityModel._dataset()
    frame = pd.DataFrame(rows)
    frame["negotiable"] = labels
    dataset_path = data_dir / "negotiability_training_v1.csv"
    frame.to_csv(dataset_path, index=False)
    model = NegotiabilityModel()
    artifact_path = artifact_dir / "negotiability-v1.joblib"
    joblib.dump({"pipeline": model.pipeline, "metrics": model.metrics}, artifact_path)
    metadata = {
        "version": "negotiability-v1",
        "algorithm": "sklearn.linear_model.LogisticRegression",
        "rows": len(rows),
        "dataset_sha256": hashlib.sha256(dataset_path.read_bytes()).hexdigest(),
        "artifact_sha256": hashlib.sha256(artifact_path.read_bytes()).hexdigest(),
        "metrics": model.metrics,
        "provenance": "DETERMINISTIC_CONTROLLED_DATASET",
    }
    (artifact_dir / "negotiability-v1.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8"
    )
    print(json.dumps(metadata, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
