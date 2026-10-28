"""Phase 0 Jev spike. Reads JEV_API_KEY from the environment (never hardcode or print it).

Purpose: record RAW responses so the real field names, latency and repeat-call stability are
known before any schema or gate code is written. Output goes to data/raw/ (git-ignored).
Untested against the live API: written from the SDK usage shown in public documentation.
"""
import asyncio, json, os, sys, time
from pathlib import Path

from typesafe_sdk import AsyncTypeSafeClient, RetryPolicy

MODEL = os.environ.get("JEV_MODEL", "jev-1.13.0")
REPEATS = 5
STATE = {  # illustrative labels only, not a market reading
    "instrument": "index option underlying",
    "candidate": "buy call",
    "trend_15m": "bullish", "trend_strength": "trending",
    "momentum": "positive", "stretch_from_value": "mild",
    "participation": "above average", "derivatives": "call OI building, IV stable",
    "session_phase": "mid morning", "event_risk": "normal",
}
QUESTIONS_FILE = Path(__file__).resolve().parent.parent / "schemas" / "jev_questions.json"


def rotations(labels):
    labels = list(labels)
    return [labels[i:] + labels[:i] for i in range(len(labels))]


def build_questions():
    spec = json.loads(QUESTIONS_FILE.read_text())["questions"]
    out = {}
    for name, q in spec.items():
        if q["type"] == "choice":
            for i, order in enumerate(rotations(q["criteria"])):
                out[f"{name}_{i}"] = {"type": "choice", "instructions": q["instructions"],
                                      "criteria": {k: q["criteria"][k] for k in order}}
        else:
            out[name] = {k: v for k, v in q.items()}
    return out


def dump(obj):
    for attr in ("model_dump", "dict"):
        if hasattr(obj, attr):
            return getattr(obj, attr)()
    return repr(obj)


async def main():
    key = (os.environ.get("JEV_API_KEY") or os.environ.get("TYPESAFE_API_KEY") or "").strip()
    if not key:
        sys.exit("set JEV_API_KEY (or TYPESAFE_API_KEY)")
    client = AsyncTypeSafeClient(api_key=key, model=MODEL, timeout=5.0, retry=RetryPolicy(max_retries=1))
    out_dir = Path("data/raw"); out_dir.mkdir(parents=True, exist_ok=True)
    questions = build_questions()
    results = []
    for i in range(REPEATS):
        t0 = time.perf_counter()
        resp = await client.system_one(state=STATE, questions=questions)
        results.append({"call": i, "latency_s": round(time.perf_counter() - t0, 3), "response": dump(resp)})
    path = out_dir / f"jev_spike_{int(time.time())}.json"
    path.write_text(json.dumps(results, indent=2, default=str))
    print(f"saved {path}; median latency {sorted(r['latency_s'] for r in results)[REPEATS // 2]}s")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:  # short, key-free error for the user to report
        sys.exit(f"Jev spike failed: {type(e).__name__}: {str(e)[:500]}")
