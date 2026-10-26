"""RAG building blocks: lexical search, rank fusion, retrieval with a fake embedder, citation guardrail.

No embedding model is loaded — vectors are tiny hand-made ones, so the tests run in milliseconds.
"""
import pytest

from backend import law, retrieval
from backend.analyzer import _format_input, enforce_citations
from backend.db import LawArticle, SessionLocal
from backend.parsing import Clause
from backend.retrieval import LawContext
from backend.schemas import ClauseAssessment, ContractAnalysis
from conftest import reset_db


def unit(i: int) -> list[float]:
    """One-hot fake embedding with the real dimension (pgvector enforces vector(768))."""
    return [1.0 if j == i else 0.0 for j in range(law.EMBED_DIM)]


ARTICLES = {  # id: (title, text, fake embedding)
    "684": ("Əmlak kirayəsi haqqının ödənilməsi müddəti", "Kirayə haqqı hər ayın sonunda ödənilməlidir.", unit(0)),
    "688": ("Bron haqqı, beh, dəbbə pulu", "Təminat bir aylıq kirayə haqqının iki mislindən çox olmamalıdır.", unit(1)),
    "691": ("Ləğvetmə barədə bildirişin müddətləri", "Yaşayış otağı üçün bildiriş ən azı üç ay əvvəl verilir.", unit(2)),
}


def test_bm25_prefix_stemming_matches_inflected_words():
    docs = [law.passage(i, t, x) for i, (t, x, _) in ARTICLES.items()]
    # "kirayəçinin" / "təminatı" do not occur verbatim — only their 5-letter prefixes do.
    plain, stemmed = law.BM25(docs), law.BM25(docs, stem=5)
    assert plain.scores("təminatı")[1] == 0
    assert max(range(3), key=lambda i: stemmed.scores("təminatı")[i]) == 1


def test_rrf_rewards_agreement_between_rankings():
    assert law.rrf(["a", "b", "c"], ["b", "c", "a"])[0] == "b"


def test_chunking_whole_articles_by_default():
    arts = [{"article": "688", "title": "T", "text": "688.1. bir\n688.1.1. alt\n688.2. iki"}]
    assert len(law.chunk_articles(arts)) == 1
    points = law.chunk_articles(arts, max_chars=5)
    assert [c["passage"].splitlines()[1] for c in points] == ["688.1. bir", "688.2. iki"]


@pytest.fixture()
def law_db(monkeypatch):
    reset_db()
    with SessionLocal() as db:
        for i, (title, text, vec) in ARTICLES.items():
            db.add(LawArticle(id=i, title=title, text=text, chapter="33", source_url="u", embedding=vec,
                              embed_model=law.current_model()))
        db.commit()
    # Fake embedder: a deposit clause points at 688, everything else at 684.
    monkeypatch.setattr(law, "embed_queries", lambda texts: [unit(1) if "depozit" in t.lower() else unit(0) for t in texts])
    yield


def test_build_context_ranks_relevant_article_first(law_db):
    clauses = [Clause(1, "Depozit qaytarılmır."), Clause(2, "Kirayə haqqı ayın 5-dək ödənilir.")]
    with SessionLocal() as db:
        ctx = retrieval.build_context(db, clauses)
    assert ctx.candidates[1][0] == "688"
    assert ctx.candidates[2][0] == "684"
    assert set(ctx.articles) == {"684", "688", "691"}  # top-5 of a 3-article corpus = all of them


def test_build_context_without_law_table_returns_none():
    reset_db()
    with SessionLocal() as db:
        assert retrieval.build_context(db, [Clause(1, "x")]) is None


def _assessment(idx, refs, explanation="izah", suggestion=""):
    return ClauseAssessment(clause_index=idx, risk="high", category="deposit",
                            explanation=explanation, suggestion=suggestion, law_refs=refs)


def test_citation_guardrail():
    ctx = LawContext(articles={"688": None, "691": None}, candidates={1: ["688"], 2: ["691"]})
    analysis = ContractAnalysis(summary="s", assessments=[
        _assessment(1, ["688", "999"]),                                       # 999 never shown to the model
        _assessment(2, [], explanation="Mülki Məcəllənin 688.4-cü maddəsinə görə ..."),  # grounded mention
        _assessment(3, [], suggestion="Maddə 700 tətbiq olunur."),             # ungrounded mention
    ])
    violations = enforce_citations(analysis, ctx)
    refs = {a.clause_index: a.law_refs for a in analysis.assessments}
    assert refs == {1: ["688"], 2: ["688"], 3: []}
    assert violations == ["bənd 1: maddə 999", "bənd 3: maddə 700"]


def test_point_level_refs_count_as_their_article():
    ctx = LawContext(articles={"688": None}, candidates={1: ["688"]})
    analysis = ContractAnalysis(summary="s", assessments=[_assessment(1, ["688.2", "Maddə 688", "688.3"])])
    assert enforce_citations(analysis, ctx) == []
    assert analysis.assessments[0].law_refs == ["688"]


def test_without_context_every_citation_is_a_violation():
    analysis = ContractAnalysis(summary="s", assessments=[_assessment(1, ["688"])])
    assert enforce_citations(analysis, None) == ["bənd 1: maddə 688"]
    assert analysis.assessments[0].law_refs == []


def test_prompt_lists_law_and_per_clause_candidates():
    art = LawArticle(id="688", title="Bron haqqı", text="688.2. ...", chapter="33", source_url="u")
    ctx = LawContext(articles={"688": art}, candidates={1: ["688", "684"]})
    prompt = _format_input([Clause(1, "Depozit qaytarılmır.")], ctx)
    assert '<article id="688" title="Bron haqqı">' in prompt
    assert '<clause index="1" candidate_articles="688, 684">Depozit qaytarılmır.</clause>' in prompt
    assert "(no articles available)" in _format_input([Clause(1, "x")], None)


def test_build_context_falls_back_to_bm25_when_embedding_fails(law_db, monkeypatch):
    def broken(texts):
        raise RuntimeError("429 quota")
    monkeypatch.setattr(law, "embed_queries", broken)
    with SessionLocal() as db:
        ctx = retrieval.build_context(db, [Clause(1, "Təminat iki aylıq kirayə haqqıdır.")])
    assert ctx.candidates[1][0] == "688"  # found lexically: "təminat", "kirayə haqqı"
