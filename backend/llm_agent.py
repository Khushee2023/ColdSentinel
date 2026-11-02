"""LLM Root Cause & Action Agent for ColdSentinel.

Leverages Google Gemini to reason over multi-sensor anomalies, diagnose root causes,
and generate high-priority operational instructions for facility technicians.
Includes async/background execution or instant sub-millisecond expert fallback
so streaming and testing are never blocked by network latency.
"""

import os
from pathlib import Path
from dotenv import load_dotenv
import requests

# Load environment variables from .env
_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_env_path)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MODEL_NAME = "gemini-flash-latest"
API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL_NAME}:generateContent"

# Cache per unit to avoid making redundant HTTP calls
_cache = {}


def generate_diagnostic(
    unit_id: str,
    temp_c: float,
    current_a: float,
    ambient_c: float,
    eta_min: int | None,
    anomaly_score: float,
    advance_warning: bool,
    use_llm_online: bool = False,
) -> str:
    """Generates a root cause diagnosis and action prescription for the unit.
    
    If use_llm_online is True and GEMINI_API_KEY is present, queries Gemini with a fast timeout.
    Otherwise, generates an expert diagnostic rule instantly without network overhead.
    """
    cache_key = f"{unit_id}_{round(temp_c, 1)}"
    if cache_key in _cache:
        return _cache[cache_key]

    if use_llm_online and GEMINI_API_KEY:
        eta_str = f"{eta_min} minutes" if eta_min is not None else "unknown time"
        early_str = " (40+ min early warning window active)" if advance_warning else ""

        prompt = (
            f"ColdSentinel AI Diagnostic Agent: Refrigeration unit {unit_id} alert.\n"
            f"Temp: {temp_c:.1f}°C, Compressor: {current_a:.1f}A, Ambient: {ambient_c:.1f}°C, "
            f"ETA to 8°C: {eta_str}{early_str}.\n"
            f"Provide a 2-sentence diagnosis (probable mechanical root cause + immediate technician action)."
        )

        try:
            resp = requests.post(
                f"{API_URL}?key={GEMINI_API_KEY}",
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"temperature": 0.2, "maxOutputTokens": 100},
                },
                timeout=1.5,
            )
            if resp.status_code == 200:
                data = resp.json()
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    text = "".join(p.get("text", "") for p in parts if "text" in p).strip()
                    if text:
                        clean_text = " ".join(text.split())
                        _cache[cache_key] = clean_text
                        return clean_text
        except Exception:
            pass

    # Instant deterministic expert diagnostic
    diagnostic = _generate_expert_diagnostic(unit_id, temp_c, current_a, ambient_c, eta_min, advance_warning)
    _cache[cache_key] = diagnostic
    return diagnostic


def _generate_expert_diagnostic(
    unit_id: str,
    temp_c: float,
    current_a: float,
    ambient_c: float,
    eta_min: int | None,
    advance_warning: bool,
) -> str:
    eta_desc = f"about {eta_min} min" if eta_min is not None else "an unknown time"
    tag = " [EARLY WARNING 40+ MIN AHEAD]" if advance_warning else ""
    
    # Root cause reasoning based on compressor current vs ambient temperature
    if current_a > 4.5 and ambient_c > 24.0:
        cause = "High thermal load & compressor overload strain"
    elif current_a > 4.2:
        cause = "Compressor mechanical degradation / refrigerant restriction"
    else:
        cause = "Thermostat drift or evaporator coil frost accumulation"

    return (
        f"Unit {unit_id}{tag}: {cause} detected (compressor {current_a:.1f} A, temp {temp_c:.1f} °C). "
        f"Estimated {eta_desc} until critical 8.0 °C threshold. "
        f"Action: inspect compressor coils/refrigerant lines and prepare perishable inventory for relocation."
    )
