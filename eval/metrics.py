"""Compute evaluation metrics from the cached runs (eval/runs/*.json) — no API calls.

Methods compared: keyword baseline, LLM without law context (norag), LLM with retrieved articles (rag).
Definitions (gold labels: eval/dataset.jsonl; "acceptable" = the set of defensible answers for borderline clauses):
  accuracy        prediction is in the clause's acceptable set
  high recall     gold=high clauses predicted as high
  flag recall     gold medium/high clauses predicted as medium or high (the tenant gets warned)
  false alarms    clauses whose only acceptable answer is low, predicted medium/high
  flag precision  medium/high predictions that are acceptable
  stability       clauses with the same prediction in every run
  law hit         clauses with an expected article: one of them is cited
  invalid refs    article numbers not backed by text given in the prompt (without RAG: every cited article)

Usage:  python eval/metrics.py   → eval/results.md, eval/results.json
"""
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.parsing import extract_text, split_clauses  # noqa: E402
from eval.baseline import classify  # noqa: E402

RISKY = {"medium", "high"}
# Prompt and baseline rules were developed while looking at 01-03; 04-05 were written afterwards.
HELD_OUT = ("kiraye_synthetic_04.txt", "kiraye_synthetic_05.txt")


def load_dataset() -> dict[tuple[str, int], dict]:
    rows = [json.loads(l) for l in (ROOT / "eval" / "dataset.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    return {(r["doc"], r["idx"]): r for r in rows}


def score(preds: dict[tuple[str, int], str], gold: dict) -> dict:
    """Classification metrics for one run (predictions keyed like the dataset)."""
    keys = [k for k in gold if k in preds]
    acc = [preds[k] in gold[k]["acceptable"] for k in keys]
    high = [preds[k] == "high" for k in keys if gold[k]["gold"] == "high"]
    flag = [preds[k] in RISKY for k in keys if gold[k]["gold"] in RISKY]
    safe = [preds[k] in RISKY for k in keys if gold[k]["acceptable"] == ["low"]]
    flagged = [preds[k] in gold[k]["acceptable"] for k in keys if preds[k] in RISKY]
    pct = lambda xs: sum(xs) / len(xs) if xs else None  # noqa: E731
    return {"n": len(keys), "accuracy": pct(acc), "high_recall": pct(high), "flag_recall": pct(flag),
            "false_alarm": pct(safe), "flag_precision": pct(flagged)}


def load_runs(runs_dir: Path) -> dict[str, list[dict]]:
    by_cond = defaultdict(list)
    for p in sorted(runs_dir.glob("*.json")):
        r = json.loads(p.read_text(encoding="utf-8"))
        by_cond[r["condition"]].append(r)
    return by_cond


def summarize(runs: list[dict], gold: dict) -> dict:
    """Mean of per-run metrics + stability + citation and cost numbers for one condition."""
    per_run = defaultdict(dict)  # run -> {(doc, idx): risk}
    refs = defaultdict(list)     # (doc, idx) -> [law_refs per run]
    for r in runs:
        for a in r["assessments"]:
            per_run[r["run"]][(r["doc"], a["clause_index"])] = a["risk"]
            refs[(r["doc"], a["clause_index"])].append(a["law_refs"])
    scores = [score(p, gold) for p in per_run.values()]
    out = {k: statistics.mean(s[k] for s in scores if s[k] is not None) for k in scores[0] if k != "n"}
    out["min_accuracy"] = min(s["accuracy"] for s in scores)
    out["max_accuracy"] = max(s["accuracy"] for s in scores)
    out["runs"] = len(per_run)

    keys = [k for k in gold if all(k in p for p in per_run.values())]
    out["stability"] = sum(len({p[k] for p in per_run.values()}) == 1 for k in keys) / len(keys)
    out["majority"] = {k: Counter(p[k] for p in per_run.values()).most_common(1)[0][0] for k in keys}

    with_law = [k for k in keys if gold[k]["law"]]
    # per (clause, run): did the citations include one of the expected articles?
    out["law_hit"] = statistics.mean(
        bool(set(cited) & set(gold[k]["law"])) for k in with_law for cited in refs[k]
    ) if with_law else None
    out["invalid_refs"] = sum(r["metrics"]["invalid_refs"] for r in runs)
    out["calls"] = len(runs)
    lat = sorted(r["metrics"]["latency_ms"] / 1000 for r in runs)
    out["latency_mean_s"] = statistics.mean(lat)
    out["latency_max_s"] = lat[-1]
    out["input_tokens_mean"] = statistics.mean(r["metrics"]["input_tokens"] for r in runs)
    out["output_tokens_mean"] = statistics.mean(r["metrics"]["output_tokens"] for r in runs)
    return out


def baseline_summary(gold: dict) -> dict:
    preds = {}
    for doc in sorted({d for d, _ in gold}):
        _, clauses = split_clauses(extract_text(doc, (ROOT / "data" / "samples" / doc).read_bytes()))
        preds |= {(doc, c.idx): classify(c.text) for c in clauses}
    s = score(preds, gold)
    s |= {"stability": 1.0, "majority": preds, "runs": 1, "law_hit": None, "invalid_refs": 0,
          "latency_mean_s": 0.0, "min_accuracy": s["accuracy"], "max_accuracy": s["accuracy"]}
    return s


def fmt(x, pct=True) -> str:
    if x is None:
        return "—"
    return f"{x:.0%}" if pct else f"{x:.1f}"


def metric_table(results: dict, cols: list[str], names: dict) -> list[str]:
    lines = ["| Metrika | " + " | ".join(names[c] for c in cols) + " |", "|---|" + "---|" * len(cols)]
    rows = [
        ("Accuracy (qəbul edilən cavab)", "accuracy"),
        ("Yüksək riskin tapılması (high → high)", "high_recall"),
        ("Riskli bəndə xəbərdarlıq (medium/high → medium/high)", "flag_recall"),
        ("Yalançı həyəcan (yalnız low olan bəndlər)", "false_alarm"),
        ("Xəbərdarlıqların dəqiqliyi (precision)", "flag_precision"),
        ("Stabillik (bütün qaçışlarda eyni cavab)", "stability"),
        ("Gözlənilən qanun maddəsinə istinad", "law_hit"),
    ]
    for title, key in rows:
        lines.append(f"| {title} | " + " | ".join(fmt(results[c].get(key)) for c in cols) + " |")
    return lines


def report(results: dict, gold: dict, held_out: dict, cov: dict) -> str:
    names = {"baseline": "Açar söz baseline", "norag": "LLM (RAG-sız)", "rag": "LLM + qanun RAG"}
    cols = [c for c in ("baseline", "norag", "rag") if c in results]
    labels = Counter(r["gold"] for r in gold.values())
    lines = [
        "# Qiymətləndirmə nəticələri",
        "",
        f"Dataset: {len(gold)} bənd, {len(cov['docs'])} / {cov['total_docs']} sintetik müqavilə (gold: high "
        f"{labels['high']}, medium {labels['medium']}, low {labels['low']}). LLM rejimləri hər müqavilə üzrə "
        f"{cov['runs']} dəfə işlədilib; rəqəmlər qaçışların ortalamasıdır. Etiketlər: `eval/dataset.jsonl`.",
        *([] if cov["complete"] else ["", "> ⚠️ **İlkin nəticə:** qiymətləndirmə hələ tamamlanmayıb (Gemini pulsuz "
                                      "limiti). Bütün üsullar eyni müqavilə və qaçışlar üzərində müqayisə olunur."]),
        "",
        "## Bütün dataset",
        "",
        *metric_table(results, cols, names),
    ]
    lines.append("| Əsaslandırılmamış maddə istinadları (cəmi) | " + " | ".join(
        str(results[c]["invalid_refs"]) if c != "baseline" else "—" for c in cols) + " |")
    lines.append("| Orta gecikmə, s | " + " | ".join(
        fmt(results[c]["latency_mean_s"], False) if c != "baseline" else "~0" for c in cols) + " |")
    lines.append("| Orta input / output token | " + " | ".join(
        f"{results[c]['input_tokens_mean']:.0f} / {results[c]['output_tokens_mean']:.0f}" if c != "baseline" else "—"
        for c in cols) + " |")
    lines.append("| Accuracy diapazonu (min–max qaçış) | " + " | ".join(
        f"{fmt(results[c]['min_accuracy'])}–{fmt(results[c]['max_accuracy'])}" for c in cols) + " |")

    n_ho = len([k for k in gold if k[0] in HELD_OUT])
    if held_out:
        lines += ["", f"## Held-out: 04 və 05 ({n_ho} bənd)", "",
              "Prompt və baseline qaydaları 01–03-ə baxaraq hazırlanıb; 04–05 sonradan yazılıb. "
              "Ədalətli müqayisə budur.", "", *metric_table(held_out, cols, names)]
    else:
        lines += ["", "## Held-out: 04 və 05", "", "Hələ işlədilməyib."]

    lines += ["", "## Səhv və sərhəd hallar (çoxluq səsi qəbul edilən dəstdə deyil)", "",
              "| Bənd | Gold | " + " | ".join(names[c] for c in cols) + " | Qeyd |", "|---|---|" + "---|" * len(cols) + "---|"]
    for k, g in gold.items():
        votes = [results[c]["majority"].get(k) for c in cols]
        if any(v not in g["acceptable"] for v in votes):
            cell = lambda v: f"**{v}**" if v not in g["acceptable"] else v  # noqa: E731
            lines.append(f"| {k[0].removeprefix('kiraye_synthetic_')} #{k[1]} | {'/'.join(g['acceptable'])} | "
                         + " | ".join(cell(v) for v in votes) + f" | {g['note']} |")
    return "\n".join(lines) + "\n"


def coverage(by_cond: dict[str, list[dict]], gold: dict) -> tuple[list[str], list[int]]:
    """Contracts and run numbers that EVERY LLM condition has, so the methods are compared on equal footing
    (the free-tier quota can stop a run halfway). Without LLM runs: all contracts."""
    docs = sorted({d for d, _ in gold})
    if not by_cond:
        return docs, []
    have = [{(r["doc"], r["run"]) for r in runs} for runs in by_cond.values()]
    common = set.intersection(*have)
    run_ids = sorted({n for _, n in common})
    docs = [d for d in docs if any((d, n) in common for n in run_ids)]
    # keep only run numbers present for every covered contract
    run_ids = [n for n in run_ids if all((d, n) in common for d in docs)]
    return docs, run_ids


def main() -> None:
    gold_all = load_dataset()
    by_cond = load_runs(ROOT / "eval" / "runs")
    docs, run_ids = coverage(by_cond, gold_all)
    gold = {k: v for k, v in gold_all.items() if k[0] in docs}
    ho_gold = {k: v for k, v in gold.items() if k[0] in HELD_OUT}
    results = {"baseline": baseline_summary(gold)}
    held_out = {"baseline": baseline_summary(ho_gold)} if ho_gold else {}
    for cond, runs in by_cond.items():
        runs = [r for r in runs if r["doc"] in docs and r["run"] in run_ids]
        if not runs:
            continue
        results[cond] = summarize(runs, gold)
        if ho_gold:
            held_out[cond] = summarize([r for r in runs if r["doc"] in HELD_OUT], ho_gold)
    all_docs = sorted({d for d, _ in gold_all})
    cov = {"docs": docs, "total_docs": len(all_docs), "clauses": len(gold), "total_clauses": len(gold_all),
           "runs": len(run_ids), "complete": docs == all_docs and len(run_ids) >= 3}
    text = report(results, gold, held_out, cov)
    (ROOT / "eval" / "results.md").write_text(text, encoding="utf-8")
    strip = lambda rs: {c: {k: v for k, v in r.items() if k != "majority"} for c, r in rs.items()}  # noqa: E731
    (ROOT / "eval" / "results.json").write_text(json.dumps(
        {"coverage": cov, "all": strip(results), "held_out": strip(held_out)}, ensure_ascii=False, indent=2,
        default=str), encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
