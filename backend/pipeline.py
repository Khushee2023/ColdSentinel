from collections import defaultdict, deque
import numpy as np
from backend.predictor import score_reading
FAIL_TEMP = 8.0                      # failure = internal temp reaches 8 C
_last_flag = defaultdict(int)        # per-unit memory of the previous reading's flag
_slopes = defaultdict(lambda: deque(maxlen=5))   # recent temperature slopes per unit


def ingest(raw: dict) -> dict:
    """Stage 1: basic validation."""
    for key in ("unit_id", "timestamp", "temp_c"):
        if key not in raw:
            raise ValueError(f"Missing field: {key}")
    return dict(raw)


def detect(r: dict) -> dict:
    """Stage 2: Isolation Forest scores the reading."""
    r["detection"] = score_reading(r)
    return r


def reason(r: dict) -> dict:
    """Stage 3: decide whether the anomaly is real or benign."""
    unit = r["unit_id"]
    flag = r["detection"]["flag"]
    consecutive = flag == 1 and _last_flag[unit] == 1
    _last_flag[unit] = flag

    # Door opened recently but compressor current is normal -> harmless
    door_event = float(r["door_opens_15m"]) > 0 and float(r["current_mean_15m"]) < 3.8

    if not flag:
        r["status"], r["reason"] = "normal", "Within normal behaviour"
    elif door_event:
        r["status"], r["reason"] = "watch", "Likely door-open event, compressor current normal"
    elif consecutive:
        r["status"], r["reason"] = "alert", "Sustained anomaly in cooling behaviour"
    else:
        r["status"], r["reason"] = "watch", "Single anomalous reading, waiting for confirmation"
    return r


def assess_risk(r: dict) -> dict:
    """Stage 4: estimate time to failure from the recent temperature trend."""
    unit = r["unit_id"]
    _slopes[unit].append(float(r["temp_slope_15m"]))
    slope = float(np.median(_slopes[unit]))      # median ignores one-off door spikes
    temp = float(r["temp_c"])
    eta = (FAIL_TEMP - temp) / slope if slope > 0.005 and temp < FAIL_TEMP else None

    if r["status"] != "alert":
        severity = None
    elif eta is not None and eta <= 20:
        severity = "critical"
    elif eta is not None and eta <= 45:
        severity = "high"
    else:
        severity = "medium"

    r["eta_min"] = round(eta) if eta is not None else None
    r["severity"] = severity
    return r


def make_alert(r: dict) -> dict:
    """Stage 5: human-readable message (plain template for now)."""
    if r["status"] == "alert":
        eta = f"about {r['eta_min']} min" if r["eta_min"] is not None else "an unknown time"
        r["message"] = (
            f"Unit {r['unit_id']}: cooling is degrading "
            f"(compressor current {float(r['current_a']):.1f} A, temp {float(r['temp_c']):.1f} C). "
            f"Estimated {eta} until {FAIL_TEMP:.0f} C. Check the compressor and move stock if needed."
        )
    else:
        r["message"] = None
    return r


def process_reading(raw: dict) -> dict:
    r = make_alert(assess_risk(reason(detect(ingest(raw)))))
    return {
        "unit_id": r["unit_id"],
        "timestamp": r["timestamp"],
        "temp_c": float(r["temp_c"]),
        "score": r["detection"]["score"],
        "status": r["status"],
        "severity": r["severity"],
        "eta_min": r["eta_min"],
        "reason": r["reason"],
        "message": r["message"],
    }

def reset_state():
    """Forget per-unit memory (used when restarting a demo)."""
    _last_flag.clear()
    _slopes.clear()