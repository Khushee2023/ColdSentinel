from flask import Flask, jsonify, render_template, request

from backend import store
from backend.pipeline import process_reading, reset_state

app = Flask(__name__)
store.init_db()


@app.route("/")
def index():
    return render_template("index.html")


@app.post("/api/ingest")
def ingest():
    """Receive one sensor reading, run it through the pipeline, save the result."""
    payload = request.get_json(silent=True)
    if not payload:
        return jsonify(error="JSON body required"), 400
    try:
        result = process_reading(payload)
    except ValueError as e:
        return jsonify(error=str(e)), 400
    store.save_result(result)
    return jsonify(result)


@app.get("/api/status")
def status():
    return jsonify(store.latest_per_unit())


@app.get("/api/alerts")
def alerts():
    return jsonify(store.recent_alerts())


@app.get("/api/history/<unit_id>")
def history(unit_id):
    return jsonify(store.history(unit_id))


@app.post("/api/reset")
def reset():
    store.clear()
    reset_state()
    return jsonify(ok=True)


if __name__ == "__main__":
    app.run(debug=True)