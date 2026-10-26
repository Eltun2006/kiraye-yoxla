"""Run the analyzer over the evaluation contracts and cache every raw result as JSON.

Conditions:  norag = LLM only;  rag = LLM + retrieved Civil Code articles (needs the law table: ingest_law.py).
Each (condition, contract, run) is one file in eval/runs/; existing files are skipped, so an interrupted run
(e.g. a free-tier rate limit) can simply be restarted. Metrics are computed offline by eval/metrics.py.

Usage:  python eval/run_eval.py [--runs 3] [--conditions norag,rag]
"""
import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.analyzer import AnalysisError, analyze_clauses  # noqa: E402
from backend.config import settings  # noqa: E402
from backend.law import current_model  # noqa: E402
from backend.parsing import extract_text, split_clauses  # noqa: E402

RUNS_DIR = ROOT / "eval" / "runs"
SAMPLES = ROOT / "data" / "samples"
PAUSE_S = 8  # stay well under the free tier's requests-per-minute limit


def eval_docs() -> list[str]:
    dataset = [json.loads(l) for l in (ROOT / "eval" / "dataset.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    return sorted({r["doc"] for r in dataset})


def run_one(doc: str, condition: str, clauses, ctx) -> dict:
    for attempt in range(4):
        try:
            analysis, metrics = analyze_clauses(clauses, ctx if condition == "rag" else None)
            return {
                "doc": doc, "condition": condition, "provider": settings.llm_provider,
                "embed_model": current_model() if condition == "rag" else None,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "metrics": metrics,
                "candidates": {str(k): v for k, v in ctx.candidates.items()} if condition == "rag" else {},
                "assessments": [a.model_dump() for a in analysis.assessments],
            }
        except AnalysisError as e:
            wait = 65 * (attempt + 1)
            print(f"   ! {e} — {wait}s gözləyirəm")
            time.sleep(wait)
    raise SystemExit("Dayandırıldı: təkrar cəhdlər bitdi. Sonra yenidən işə salın (hazır nəticələr saxlanılıb).")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--conditions", default="norag,rag")
    args = ap.parse_args()
    conditions = args.conditions.split(",")
    RUNS_DIR.mkdir(parents=True, exist_ok=True)

    ctx_by_doc = {}
    for doc in eval_docs():
        _, clauses = split_clauses(extract_text(doc, (SAMPLES / doc).read_bytes()))
        if "rag" in conditions:
            from backend.db import SessionLocal
            from backend.retrieval import build_context

            with SessionLocal() as db:
                ctx_by_doc[doc] = build_context(db, clauses)
            if ctx_by_doc[doc] is None:
                raise SystemExit("Qanun cədvəli boşdur — əvvəlcə scripts/ingest_law.py işlədin.")
        for run in range(1, args.runs + 1):
            for cond in conditions:
                out = RUNS_DIR / f"{cond}__{Path(doc).stem}__r{run}.json"
                if out.exists():
                    continue
                print(f"{cond:<6} {doc:<28} run {run} ...", flush=True)
                result = run_one(doc, cond, clauses, ctx_by_doc.get(doc))
                result["run"] = run
                out.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
                m = result["metrics"]
                print(f"   ✓ {m['latency_ms'] / 1000:.1f}s, in {m['input_tokens']}, out {m['output_tokens']}, invalid_refs {m['invalid_refs']}")
                time.sleep(PAUSE_S)


if __name__ == "__main__":
    main()
