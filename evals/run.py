"""Run the golden dataset through the real agent (via the API) and grade every output.

    .venv/bin/python -m evals.run                     # all cases
    .venv/bin/python -m evals.run minutes voicebot    # some cases
    SELF_CHECK=0 .venv/bin/python -m evals.run        # the same, with the self-check off (ablation)

Cases are spaced out so the free model tiers' per-minute limits can recover between them.
"""
import io
import json
import logging
import os
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

from fastapi.testclient import TestClient

from app import api, config
from app.models import Task
from app.tools import lookup_mock_data
from evals.cases import CASES
from evals.graders import deterministic, judge

GAP_S = int(os.getenv("EVAL_GAP_S", "40"))
RESULTS = Path(__file__).parent / "results"


def run(ids: list[str]) -> None:
    client = TestClient(api.app)
    cases = [c for c in CASES if not ids or c.id in ids]
    log_buffer = io.StringIO()
    handler = logging.StreamHandler(log_buffer)
    logging.getLogger("agent.llm").addHandler(handler)
    rows = []
    for n, case in enumerate(cases):
        if n:
            time.sleep(GAP_S)
        log_buffer.truncate(0), log_buffer.seek(0)
        started = time.perf_counter()
        r = client.post("/agent", json={"request": case.request})
        seconds = round(time.perf_counter() - started, 1)
        body = r.json() if r.headers.get("content-type", "").startswith("application/json") else None
        response = body if r.status_code == 200 else None
        path = None
        if response:
            doc_id = response["document_url"].rsplit("/", 1)[-1]
            path = next(config.OUTPUT_DIR.glob(f"*{doc_id}.docx"), None)
        checks = deterministic(case, response, r.status_code, path)
        verdict = None
        if path:
            facts = lookup_mock_data(Task(id=0, title="", tool="lookup_mock_data", instruction=""), case.request)
            verdict = judge(case, path, facts)
        answered = Counter(l.split("answered by ")[1].split(" ")[0] for l in log_buffer.getvalue().splitlines() if "answered by" in l)
        rows.append({"case": case.id, "category": case.category, "status": r.status_code, "seconds": seconds,
                     "llm_calls": sum(answered.values()), "models": dict(answered), "checks": checks,
                     "judge": verdict.model_dump() if verdict else None,
                     "self_check": (response or {}).get("self_check"), "detail": None if response else body})
        print(f"[{n + 1}/{len(cases)}] {case.id}: {r.status_code} in {seconds}s, "
              + ", ".join(f"{k}={'✓' if v else '✗'}" for k, v in checks.items() if v is not None), flush=True)
    report(rows)


def report(rows: list[dict]) -> None:
    mode = "self-check ON" if config.SELF_CHECK else "self-check OFF"
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / f"{stamp}-{'on' if config.SELF_CHECK else 'off'}.json"
    out.write_text(json.dumps(rows, indent=2, ensure_ascii=False))

    names = sorted({k for r in rows for k, v in r["checks"].items() if v is not None})
    judge_keys = ["answers_the_request", "contradicts_the_records", "ready_to_send"]
    print(f"\n## Eval results ({mode}, {len(rows)} cases) → {out.name}\n")
    print("| case | " + " | ".join(names) + " | judge: answers / no contradiction / ready | s | calls |")
    print("|" + "---|" * (len(names) + 4))
    for r in rows:
        cells = ["–" if r["checks"].get(k) is None else ("✓" if r["checks"][k] else "✗") for k in names]
        j = r["judge"]
        jcell = " / ".join("✓" if (j[k] if k != "contradicts_the_records" else not j[k]) else "✗" for k in judge_keys) if j else "–"
        print(f"| {r['case']} | " + " | ".join(cells) + f" | {jcell} | {r['seconds']} | {r['llm_calls']} |")
    print("\n**Pass rate per check** (cases where it applies):")
    for k in names:
        vals = [r["checks"][k] for r in rows if r["checks"].get(k) is not None]
        print(f"- {k}: {sum(vals)}/{len(vals)}")
    judged = [r["judge"] for r in rows if r["judge"]]
    for k in judge_keys:
        good = sum((not j[k]) if k == "contradicts_the_records" else j[k] for j in judged)
        print(f"- judge {k.replace('_', ' ')}{' (no)' if k == 'contradicts_the_records' else ''}: {good}/{len(judged)}")
    secs = sorted(r["seconds"] for r in rows if r["status"] == 200)
    if secs:
        print(f"- latency: median {secs[len(secs) // 2]}s, max {secs[-1]}s")


if __name__ == "__main__":
    run(sys.argv[1:])
