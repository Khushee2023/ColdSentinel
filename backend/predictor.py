from pathlib import Path
import joblib
import pandas as pd

MODEL_PATH = Path(__file__).resolve().parent.parent / "model" / "iforest.joblib"

# Load once when the app starts, not on every request
_bundle = joblib.load(MODEL_PATH)
_model = _bundle["model"]
FEATURES = _bundle["features"]
THRESHOLD = _bundle["threshold"]


def score_reading(reading: dict) -> dict:
    """Score one sensor reading. Higher score = more anomalous."""
    missing = [f for f in FEATURES if f not in reading]
    if missing:
        raise ValueError(f"Missing features: {missing}")

    X = pd.DataFrame([{f: float(reading[f]) for f in FEATURES}])
    score = float(-_model.score_samples(X)[0])

    return {
        "score": round(score, 4),
        "flag": int(score > THRESHOLD),
        "threshold": round(THRESHOLD, 4),
    }