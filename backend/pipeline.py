"""5-Agent LangGraph Pipeline for ColdSentinel.

Architected as a 5-agent LangGraph StateGraph pipeline combining Machine Learning
(Isolation Forest) and contextual reasoning over telemetry signals to predict
cold chain failure 40+ minutes in advance.

Agents in Pipeline:
1. Ingestion Agent (Telemetry Validation & Preprocessing)
2. ML Anomaly Detection Agent (Isolation Forest feature scoring)
3. Contextual Reasoning Agent (Door event vs compressor degradation reasoning)
4. Predictive Risk & Prognostics Agent (Rolling slope & 40+ min ETA to failure)
5. Action & Alert Dispatch Agent (Severity assignment & mitigation instructions)
"""

from collections import defaultdict, deque
from typing import Optional, TypedDict
import numpy as np

from langgraph.graph import StateGraph, START, END
from backend.predictor import score_reading

FAIL_TEMP = 8.0  # critical threshold where cold-chain products spoil
_last_flag = defaultdict(int)  # per-unit memory of previous anomaly flag
_slopes = defaultdict(lambda: deque(maxlen=5))  # rolling temperature slopes per unit


class PipelineState(TypedDict):
    """Shared state passed between agents in the LangGraph graph."""
    # Input Telemetry
    raw: dict
    unit_id: str
    timestamp: str
    temp_c: float
    ambient_c: float
    door_open: int
    compressor_on: int
    current_a: float
    temp_slope_15m: float
    door_opens_15m: float
    current_mean_15m: float

    # Agent 2: ML Detection
    detection: dict
    score: float
    flag: int

    # Agent 3: Contextual Reasoning
    status: str
    reason: str
    is_door_event: bool

    # Agent 4: Risk & Prognostics (ETA prediction 40+ min ahead)
    slope: float
    eta_min: Optional[float]
    severity: Optional[str]
    advance_warning: bool

    # Agent 5: Action & Dispatch
    message: Optional[str]
    action_required: bool


# ---------------------------------------------------------------------------
# Agent 1: Ingestion & Telemetry Validation Agent
# ---------------------------------------------------------------------------
def ingestion_agent(state: PipelineState) -> dict:
    """Agent 1: Validates raw IoT packet, casts numeric fields, ensures data sanity."""
    raw = state["raw"]
    for key in ("unit_id", "timestamp", "temp_c"):
        if key not in raw:
            raise ValueError(f"Missing mandatory telemetry field: {key}")

    return {
        "unit_id": str(raw["unit_id"]),
        "timestamp": str(raw["timestamp"]),
        "temp_c": float(raw["temp_c"]),
        "ambient_c": float(raw.get("ambient_c", 20.0)),
        "door_open": int(raw.get("door_open", 0)),
        "compressor_on": int(raw.get("compressor_on", 1)),
        "current_a": float(raw.get("current_a", 0.0)),
        "temp_slope_15m": float(raw.get("temp_slope_15m", 0.0)),
        "door_opens_15m": float(raw.get("door_opens_15m", 0.0)),
        "current_mean_15m": float(raw.get("current_mean_15m", 0.0)),
    }


# ---------------------------------------------------------------------------
# Agent 2: ML Anomaly Detection Agent
# ---------------------------------------------------------------------------
def ml_detection_agent(state: PipelineState) -> dict:
    """Agent 2: Runs Isolation Forest ML model over 12 sensor features."""
    detection = score_reading(state["raw"])
    return {
        "detection": detection,
        "score": detection["score"],
        "flag": detection["flag"],
    }


# ---------------------------------------------------------------------------
# Agent 3: Contextual Reasoning Agent
# ---------------------------------------------------------------------------
def contextual_reasoning_agent(state: PipelineState) -> dict:
    """Agent 3: Distinguishes benign door-opens from genuine refrigeration degradation.
    
    Suppresses false alarms if door activity is observed while compressor current
    remains nominal. Confirms true alerts when anomalies are sustained.
    """
    unit = state["unit_id"]
    flag = state["flag"]
    consecutive = flag == 1 and _last_flag[unit] == 1
    _last_flag[unit] = flag

    door_event = state["door_opens_15m"] > 0 and state["current_mean_15m"] < 3.8

    if not flag:
        status, reason = "normal", "Within normal operating envelope"
    elif door_event:
        status, reason = "watch", "Likely door-open event; compressor current remains normal"
    elif consecutive:
        status, reason = "alert", "Sustained anomaly in refrigeration / compressor behaviour"
    else:
        status, reason = "watch", "Single anomalous sensor vector; awaiting temporal confirmation"

    return {
        "status": status,
        "reason": reason,
        "is_door_event": door_event,
    }


# ---------------------------------------------------------------------------
# Agent 4: Risk & Prognostics Agent (Predicting failure 40+ min in advance)
# ---------------------------------------------------------------------------
def risk_prognostics_agent(state: PipelineState) -> dict:
    """Agent 4: Calculates temperature trajectory slope and prognostic ETA to 8°C.
    
    Evaluates early-warning windows (40+ minutes in advance of threshold breach)
    and computes dynamic severity levels.
    """
    unit = state["unit_id"]
    _slopes[unit].append(state["temp_slope_15m"])
    slope = float(np.median(_slopes[unit]))
    temp = state["temp_c"]

    # Linear trajectory to critical 8°C failure mark
    eta = (FAIL_TEMP - temp) / slope if slope > 0.005 and temp < FAIL_TEMP else None

    if state["status"] != "alert":
        severity = None
    elif eta is not None and eta <= 20:
        severity = "critical"
    elif eta is not None and eta <= 45:
        severity = "high"
    else:
        severity = "medium"

    advance_warning = eta is not None and eta >= 40

    return {
        "slope": slope,
        "eta_min": round(eta) if eta is not None else None,
        "severity": severity,
        "advance_warning": advance_warning,
    }


# ---------------------------------------------------------------------------
# Agent 5: Action & Alert Dispatch Agent
# ---------------------------------------------------------------------------
def action_dispatch_agent(state: PipelineState) -> dict:
    """Agent 5: Formulates targeted operational actions and dispatch messages."""
    if state["status"] == "alert":
        eta_desc = f"about {state['eta_min']} min" if state["eta_min"] is not None else "an unknown time"
        early_note = " [EARLY WARNING 40+ MIN AHEAD]" if state.get("advance_warning") else ""
        msg = (
            f"Unit {state['unit_id']}{early_note}: cooling degradation detected "
            f"(compressor current {state['current_a']:.1f} A, temp {state['temp_c']:.1f} °C). "
            f"Estimated {eta_desc} until critical {FAIL_TEMP:.0f} °C limit. "
            f"Action: inspect compressor coils/refrigerant and transfer perishable stock."
        )
        action_req = True
    else:
        msg = None
        action_req = False

    return {
        "message": msg,
        "action_required": action_req,
    }


# ---------------------------------------------------------------------------
# Build LangGraph 5-Agent Workflow
# ---------------------------------------------------------------------------
def create_cold_sentinel_graph():
    graph = StateGraph(PipelineState)

    # Register 5 specialized agents
    graph.add_node("ingestion_agent", ingestion_agent)
    graph.add_node("ml_detection_agent", ml_detection_agent)
    graph.add_node("contextual_reasoning_agent", contextual_reasoning_agent)
    graph.add_node("risk_prognostics_agent", risk_prognostics_agent)
    graph.add_node("action_dispatch_agent", action_dispatch_agent)

    # Define sequential agent transitions
    graph.add_edge(START, "ingestion_agent")
    graph.add_edge("ingestion_agent", "ml_detection_agent")
    graph.add_edge("ml_detection_agent", "contextual_reasoning_agent")
    graph.add_edge("contextual_reasoning_agent", "risk_prognostics_agent")
    graph.add_edge("risk_prognostics_agent", "action_dispatch_agent")
    graph.add_edge("action_dispatch_agent", END)

    return graph.compile()


# Compile graph once for fast execution
_agent_graph = create_cold_sentinel_graph()


def process_reading(raw: dict) -> dict:
    """Execute reading through the compiled 5-Agent LangGraph pipeline."""
    initial_state = {"raw": raw}
    final_state = _agent_graph.invoke(initial_state)

    return {
        "unit_id": final_state["unit_id"],
        "timestamp": final_state["timestamp"],
        "temp_c": float(final_state["temp_c"]),
        "score": round(float(final_state["score"]), 4),
        "status": final_state["status"],
        "severity": final_state["severity"],
        "eta_min": final_state["eta_min"],
        "reason": final_state["reason"],
        "message": final_state["message"],
    }


def reset_state():
    """Reset agent in-memory state."""
    _last_flag.clear()
    _slopes.clear()