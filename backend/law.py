"""Law corpus: loading, local embeddings (no API key, no cost) and lexical search.

Retrieval design (chosen with eval/retrieval_eval.py, see eval/retrieval_results.json):
  hybrid = multilingual-e5-base (dense, stored in pgvector) + BM25 over 5-char prefixes (lexical),
  fused with Reciprocal Rank Fusion, over WHOLE articles. On 20 labeled clauses this gave hit@5 = 90%,
  vs. 60-70% for e5 alone and 85% for BM25 alone; splitting articles into points did not help.
"""
import json
import math
import re
import threading
from collections import Counter
from functools import lru_cache
from pathlib import Path

LAW_FILE = Path(__file__).resolve().parents[1] / "data" / "law" / "mulki_mecelle_fesil33.json"
EMBED_MODEL = "intfloat/multilingual-e5-base"
EMBED_DIM = 768
STEM = 5  # BM25 compares the first 5 letters of each word

_TOP_POINT = re.compile(r"^(\d+(?:-\d+)?\.\d+)\.\s")  # "688.2. ..." but not "688.1.3. ..."


def load_articles(path: Path = LAW_FILE) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def passage(article: str, title: str, text: str) -> str:
    """What gets embedded, searched and shown to the LLM: heading + body."""
    return f"Maddə {article}. {title}\n{text}"


def chunk_articles(articles: list[dict], max_chars: int | None = None) -> list[dict]:
    """Whole articles by default; with max_chars, longer ones are split into top-level points (eval only)."""
    chunks = []
    for a in articles:
        if max_chars is None or len(a["text"]) <= max_chars:
            chunks.append({"article": a["article"], "passage": passage(a["article"], a["title"], a["text"])})
            continue
        groups: list[list[str]] = []
        for line in a["text"].splitlines():
            if _TOP_POINT.match(line) or not groups:
                groups.append([line])
            else:
                groups[-1].append(line)
        chunks += [{"article": a["article"], "passage": passage(a["article"], a["title"], "\n".join(g))} for g in groups]
    return chunks


# ---------- dense: embeddings ----------
_model_lock = threading.Lock()


@lru_cache(maxsize=2)
def _load_model(name: str):
    from sentence_transformers import SentenceTransformer  # heavy import: load lazily, once

    return SentenceTransformer(name, device="cpu")


def _model(name: str):
    # lru_cache alone is not thread-safe: the startup warm-up thread and an analysis arriving at the same time
    # would each load a ~1 GB model. The lock makes the second caller wait for the first one's result.
    with _model_lock:
        return _load_model(name)


def _prefix(model: str, kind: str) -> str:
    # e5 models are trained with "query: " / "passage: " prefixes.
    return f"{kind}: " if "e5" in model else ""


def embed_passages(texts: list[str], model: str = EMBED_MODEL) -> list[list[float]]:
    # normalized vectors make dot product = cosine similarity
    p = _prefix(model, "passage")
    return _model(model).encode([p + t for t in texts], normalize_embeddings=True, batch_size=8).tolist()


def embed_queries(texts: list[str], model: str = EMBED_MODEL) -> list[list[float]]:
    p = _prefix(model, "query")
    return _model(model).encode([p + t for t in texts], normalize_embeddings=True, batch_size=8).tolist()


# ---------- lexical: BM25 ----------
def tokenize(text: str, stem: int = 0) -> list[str]:
    # Azerbaijani is agglutinative ("kirayəçiyə", "kirayəçinin"): truncating to a prefix is a cheap stemmer.
    toks = re.findall(r"\w+", text.lower())
    return [t[:stem] for t in toks] if stem else toks


class BM25:
    def __init__(self, docs: list[str], stem: int = 0, k1: float = 1.5, b: float = 0.75):
        self.stem = stem
        self.docs = [tokenize(d, stem) for d in docs]
        self.avgdl = sum(map(len, self.docs)) / len(self.docs)
        df = Counter(t for d in self.docs for t in set(d))
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}
        self.tf = [Counter(d) for d in self.docs]
        self.k1, self.b = k1, b

    def scores(self, query: str) -> list[float]:
        q = tokenize(query, self.stem)
        out = []
        for tf, d in zip(self.tf, self.docs):
            s = 0.0
            for t in q:
                if t in tf:
                    f = tf[t]
                    s += self.idf[t] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * len(d) / self.avgdl))
            out.append(s)
        return out


def rrf(*rankings: list[str], k: int = 60) -> list[str]:
    """Reciprocal Rank Fusion: merge ranked id lists without normalizing incompatible score scales."""
    score: dict[str, float] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, start=1):
            score[item] = score.get(item, 0.0) + 1 / (k + rank)
    return sorted(score, key=score.get, reverse=True)
