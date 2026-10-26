"""Law corpus: loading, embeddings and lexical search.

Retrieval design (chosen with eval/retrieval_eval.py, see eval/retrieval_results.json):
  dense embeddings (stored in pgvector) over WHOLE articles; splitting articles into points did not help.
  gemini-embedding-001 alone: hit@5 100%. The local e5-base alone only reaches 70%, so with it the dense
  ranking is fused with BM25 over 5-char prefixes via Reciprocal Rank Fusion (90%). BM25 alone (85%) is
  the fallback when the embedding API fails.

Two embedding providers (EMBED_PROVIDER):
  - "gemini": Gemini Embedding API — no model in RAM, so the app fits a 512 MB free server (deployment default)
  - "local":  intfloat/multilingual-e5-base via sentence-transformers (~1.5 GB RAM, offline, no quota)
Vectors of different models are not comparable: every stored vector records its model (LawArticle.embed_model).
"""
import json
import math
import re
import threading
import time
from collections import Counter
from functools import lru_cache
from pathlib import Path

import numpy as np

LAW_FILE = Path(__file__).resolve().parents[1] / "data" / "law" / "mulki_mecelle_fesil33.json"
EMBED_MODEL = "intfloat/multilingual-e5-base"  # the local model
EMBED_DIM = 768  # pgvector column size; Gemini is asked for the same size (output_dimensionality)
GEMINI_BATCH = 8      # texts per request: smaller batches spread over the per-minute token limit
GEMINI_RETRY_S = 30
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
def current_model() -> str:
    """The embedding model in use; rows embedded with any other model are ignored by retrieval."""
    from .config import settings

    return settings.gemini_embed_model if settings.embed_provider == "gemini" else EMBED_MODEL


_gemini_client = None


def _gemini_embed(texts: list[str], model: str, task: str) -> list[list[float]]:
    from google import genai
    from google.genai import errors, types

    from .config import settings

    global _gemini_client
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")
    if _gemini_client is None:
        _gemini_client = genai.Client(api_key=settings.gemini_api_key)
    vecs = []
    for i in range(0, len(texts), GEMINI_BATCH):
        for attempt in range(4):
            try:
                r = _gemini_client.models.embed_content(
                    model=model, contents=texts[i:i + GEMINI_BATCH],
                    config=types.EmbedContentConfig(task_type=task, output_dimensionality=EMBED_DIM),
                )
                break
            except errors.APIError as e:
                # Free tier: 30k tokens per minute. Ingesting the whole chapter exceeds it — wait for the window.
                if e.code != 429 or attempt == 3:
                    raise
                time.sleep(GEMINI_RETRY_S)
        vecs += [e.values for e in r.embeddings]
    # Truncated (768 of 3072) Gemini vectors are not unit length: normalize so dot product = cosine.
    m = np.array(vecs, dtype=float)
    return (m / np.linalg.norm(m, axis=1, keepdims=True)).tolist()


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


def embed_passages(texts: list[str], model: str | None = None) -> list[list[float]]:
    # normalized vectors make dot product = cosine similarity
    model = model or current_model()
    if model.startswith("gemini"):
        return _gemini_embed(texts, model, "RETRIEVAL_DOCUMENT")
    p = _prefix(model, "passage")
    return _model(model).encode([p + t for t in texts], normalize_embeddings=True, batch_size=8).tolist()


def embed_queries(texts: list[str], model: str | None = None) -> list[list[float]]:
    model = model or current_model()
    if model.startswith("gemini"):
        return _gemini_embed(texts, model, "RETRIEVAL_QUERY")
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
