from backend import store

store.init_db()
store.clear()

store.save_result({"unit_id": "A", "timestamp": "06:10", "temp_c": 4.7, "score": 0.44,
                   "status": "normal", "severity": None, "eta_min": None,
                   "reason": "Within normal behaviour", "message": None})
store.save_result({"unit_id": "C", "timestamp": "11:15", "temp_c": 5.9, "score": 0.66,
                   "status": "alert", "severity": "high", "eta_min": 37,
                   "reason": "Sustained anomaly", "message": "Unit C: cooling is degrading"})

print("latest:", store.latest_per_unit())
print("alerts:", store.recent_alerts())
print("history C:", store.history("C"))

store.clear()
print("cleared, rows left:", len(store.latest_per_unit()))