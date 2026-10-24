"""API flow test with the LLM mocked out — runs offline, no API key or cost.

Run: python -m pytest -q
"""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import backend.main as main
from backend.config import settings
from backend.db import Analysis, LawArticle, SessionLocal
from backend.parsing import extract_text, split_clauses
from backend.schemas import ClauseAssessment, ContractAnalysis
from conftest import reset_db

SAMPLE = Path(__file__).resolve().parents[1] / "data" / "samples" / "kiraye_synthetic_01.txt"


def fake_analyze(clauses, ctx=None):
    return ContractAnalysis(
        summary="test",
        assessments=[
            ClauseAssessment(
                clause_index=c.idx,
                risk="high" if c.idx == 5 else "low",
                category="deposit" if c.idx == 5 else "general",
                explanation="izah",
                suggestion="Depozit müqavilə bitdikdə qaytarılır." if c.idx == 5 else "",
                law_refs=["688"] if c.idx == 5 else [],
            )
            for c in clauses
        ],
    ), {"model": "fake", "cost_usd": 0.01, "latency_ms": 5}


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(main, "analyze_clauses", fake_analyze)
    monkeypatch.setattr(main, "build_context", lambda db, clauses: None)  # no embedding model in tests
    monkeypatch.setattr(main, "limiter", main.RateLimiter(1000, 3600))   # rate limits get their own tests
    monkeypatch.setattr(settings, "daily_analysis_limit", 1000)
    reset_db()  # every test starts from an empty database
    with TestClient(main.app) as c:
        yield c


def test_split_sample_into_13_clauses():
    _, clauses = split_clauses(extract_text(SAMPLE.name, SAMPLE.read_bytes()))
    assert len(clauses) == 13
    assert clauses[4].text.startswith("Kirayəçi müqavilə bağlanarkən 1200 manat")


def test_full_flow(client):
    r = client.post("/analyses", files={"file": (SAMPLE.name, SAMPLE.read_bytes())})
    assert r.status_code == 202
    a = client.get(f"/analyses/{r.json()['id']}").json()
    assert a["status"] == "done" and len(a["clauses"]) == 13

    deposit = next(c for c in a["clauses"] if c["idx"] == 5)
    assert client.patch(f"/analyses/{a['id']}/clauses/{deposit['id']}", json={"decision": "accepted"}).status_code == 200

    report = client.get(f"/analyses/{a['id']}/report.md").text
    assert "Depozit müqavilə bitdikdə qaytarılır." in report.split("danışıq mesajı")[1]


def test_frontend_and_samples(client):
    assert "KirayəYoxla" in client.get("/").text
    assert client.get("/static/app.js").status_code == 200
    samples = {s["name"]: s for s in client.get("/samples").json()}
    assert samples["kiraye_synthetic_01.txt"]["clauses"] == 13
    assert samples["kiraye_synthetic_02.docx"]["format"] == "DOCX"
    assert client.get("/samples/kiraye_synthetic_03.pdf").content.startswith(b"%PDF")
    assert client.get("/samples/..%2F.env").status_code == 404


def test_message_only_from_accepted(client):
    r = client.post("/analyses", files={"file": (SAMPLE.name, SAMPLE.read_bytes())})
    aid = r.json()["id"]
    assert "Heç bir təklif" in client.get(f"/analyses/{aid}/message").text
    deposit = next(c for c in client.get(f"/analyses/{aid}").json()["clauses"] if c["idx"] == 5)
    client.patch(f"/analyses/{aid}/clauses/{deposit['id']}", json={"decision": "edited", "user_text": "Depozit 30 gün ərzində qaytarılır."})
    assert "Bənd 5: Depozit 30 gün ərzində qaytarılır." in client.get(f"/analyses/{aid}/message").text


def test_bad_inputs(client):
    assert client.post("/analyses", data={"text": "   "}).status_code == 400
    r = client.post("/analyses", files={"file": ("x.exe", b"abc")})
    assert r.status_code == 415 and ".pdf" in r.json()["detail"]


def test_edit_requires_text(client):
    aid = client.post("/analyses", files={"file": (SAMPLE.name, SAMPLE.read_bytes())}).json()["id"]
    cid = client.get(f"/analyses/{aid}").json()["clauses"][0]["id"]
    assert client.patch(f"/analyses/{aid}/clauses/{cid}", json={"decision": "edited", "user_text": ""}).status_code == 400


def test_cited_articles_are_returned_and_reported(client):
    with SessionLocal() as db:
        db.add(LawArticle(id="688", title="Bron haqqı, beh, dəbbə pulu", text="688.2. ... iki mislindən çox olmamalıdır.",
                          chapter="33-cü fəsil", source_url="https://e-qanun.az/framework/46944", embedding=None))
        db.commit()
    r = client.post("/analyses", files={"file": (SAMPLE.name, SAMPLE.read_bytes())})
    a = client.get(f"/analyses/{r.json()['id']}").json()

    deposit = next(c for c in a["clauses"] if c["idx"] == 5)
    assert deposit["law_refs"] == ["688"]
    assert [l["id"] for l in a["laws"]] == ["688"] and "iki mislindən" in a["laws"][0]["text"]
    report = client.get(f"/analyses/{a['id']}/report.md").text
    assert "Mülki Məcəllə, maddə 688" in report and "e-qanun.az" in report
