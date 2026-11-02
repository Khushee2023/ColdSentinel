import argparse
import time

import pandas as pd
import requests

URL = "http://127.0.0.1:5000"

FEATURES = [
    "temp_c", "ambient_c", "door_open", "compressor_on", "current_a",
    "temp_mean_15m", "temp_std_15m", "temp_slope_15m", "current_mean_15m",
    "duty_cycle_15m", "door_opens_15m", "temp_dev_setpoint",
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--delay", type=float, default=0.5, help="seconds between readings")
    ap.add_argument("--keep", action="store_true", help="do not clear existing data first")
    args = ap.parse_args()

    df = pd.read_csv("data/coldsentinel.csv")
    # interleave the units so they advance together, like real sensors
    df = df.sort_values(["timestamp", "unit_id"], kind="stable")

    if not args.keep:
        requests.post(f"{URL}/api/reset", timeout=10)

    for _, row in df.iterrows():
        payload = {"unit_id": str(row["unit_id"]), "timestamp": str(row["timestamp"])}
        payload.update({f: float(row[f]) for f in FEATURES})

        resp = requests.post(f"{URL}/api/ingest", json=payload, timeout=10)
        resp.raise_for_status()
        r = resp.json()

        if r["status"] != "normal":
            print(f"{r['timestamp']} unit {r['unit_id']}: {r['status'].upper()} "
                  f"(score {r['score']}, severity {r['severity']}, eta {r['eta_min']}) - {r['reason']}")

        time.sleep(args.delay)

    print("replay finished")


if __name__ == "__main__":
    main()