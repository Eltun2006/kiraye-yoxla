"""Evaluation metrics: definitions checked on tiny hand-made data, so the reported numbers can be trusted."""
import pytest

from eval.baseline import classify
from eval.metrics import score, summarize

GOLD = {
    ("d", 1): {"gold": "high", "acceptable": ["high"], "law": ["688"]},
    ("d", 2): {"gold": "medium", "acceptable": ["medium", "high"], "law": []},
    ("d", 3): {"gold": "low", "acceptable": ["low"], "law": []},
    ("d", 4): {"gold": "low", "acceptable": ["low", "medium"], "law": []},  # borderline
}


def test_score_definitions():
    s = score({("d", 1): "medium", ("d", 2): "high", ("d", 3): "medium", ("d", 4): "medium"}, GOLD)
    assert s["accuracy"] == 0.5          # 2 and 4 acceptable; 1 too mild, 3 false alarm
    assert s["high_recall"] == 0.0       # the only high clause was called medium
    assert s["flag_recall"] == 1.0       # ...but both risky clauses were flagged
    assert s["false_alarm"] == 1.0       # clause 3 (only "low" acceptable) was flagged
    assert s["flag_precision"] == pytest.approx(2 / 4)  # flags on 1, 2, 3, 4 — acceptable on 2 and 4


def _run(run, risks, refs=None, invalid=0):
    return {"doc": "d", "run": run, "metrics": {"invalid_refs": invalid, "latency_ms": 1000,
                                                "input_tokens": 10, "output_tokens": 5},
            "assessments": [{"clause_index": i, "risk": r, "law_refs": (refs or {}).get(i, [])}
                            for i, r in enumerate(risks, start=1)]}


def test_summarize_stability_citations_and_majority():
    runs = [_run(1, ["high", "medium", "low", "low"], {1: ["688"]}),
            _run(2, ["high", "high", "low", "low"], {1: ["684"]}, invalid=1),
            _run(3, ["high", "medium", "low", "medium"], {1: ["688", "680"]})]
    s = summarize(runs, GOLD)
    assert s["stability"] == 0.5         # clauses 1 and 3 identical in all runs; 2 and 4 changed
    assert s["majority"][("d", 2)] == "medium"
    assert s["law_hit"] == pytest.approx(2 / 3)  # 688 cited in runs 1 and 3
    assert s["invalid_refs"] == 1 and s["accuracy"] == 1.0


def test_baseline_rules():
    assert classify("Depozit heç bir halda qaytarılmır.") == "high"
    assert classify("Ödəniş gecikdikdə cərimə ödənilir.") == "medium"
    assert classify("Müqavilə iki nüsxədə tərtib edilir.") == "low"
