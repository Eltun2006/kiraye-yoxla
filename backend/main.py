"""FastAPI backend + static frontend. Run: uvicorn backend.main:app --reload  → http://localhost:8000"""
import json
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import selectinload

from .analyzer import AnalysisError, analyze_clauses
from .config import settings
from .db import Analysis, ClauseRow, LawArticle, SessionLocal, init_db
from .ingest import has_law, ingest_law
from .law import EMBED_MODEL, _model, current_model
from .parsing import ParseError, extract_text, split_clauses
from .report import build_message, build_report
from .retrieval import build_context
from .schemas import AnalysisOut, ClauseOut, DecisionIn, LawOut
from .security import CSP, SECURITY_HEADERS, RateLimiter, check_upload, client_ip

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
SAMPLES = ROOT / "data" / "samples"
EVAL = ROOT / "eval"

limiter = RateLimiter(settings.rate_limit_per_hour, window_s=3600)


def purge_expired(db) -> int:
    """Delete analyses older than the retention period (contracts can contain personal data)."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.retention_days)
    old = select(Analysis.id).where(Analysis.created_at < cutoff)
    db.execute(delete(ClauseRow).where(ClauseRow.analysis_id.in_(old)))
    n = db.execute(delete(Analysis).where(Analysis.created_at < cutoff)).rowcount
    db.commit()
    return n


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    with SessionLocal() as db:
        # Background tasks die with the process: analyses that were running at shutdown would poll forever.
        db.execute(
            update(Analysis)
            .where(Analysis.status.in_(("queued", "parsing", "analyzing")))
            .values(status="failed", error="Server yenidən başladı və analiz yarımçıq qaldı. Yenidən cəhd edin.")
        )
        db.commit()
        purge_expired(db)
        law_ready = has_law(db)
    if (law_ready and settings.embed_provider == "local") or (not law_ready and settings.auto_ingest_law):
        # In the background: the server answers immediately; analyses started meanwhile simply wait for the
        # model lock (or run without citations if the law table is still empty).
        threading.Thread(target=_warm_up, args=(law_ready,), daemon=True).start()
    yield


def _warm_up(law_ready: bool) -> None:
    try:
        if not law_ready:
            with SessionLocal() as db:
                print(f"[law] no vectors for {current_model()}, auto-ingested {ingest_law(db)} articles")
        elif current_model() == EMBED_MODEL:
            _model(EMBED_MODEL)  # local model: so the first analysis doesn't wait ~20 s to load it
    except Exception as e:  # never take the app down: analyses still work, just without citations
        print(f"[law] warm-up failed: {e!r}")


app = FastAPI(title="KirayəYoxla API", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=FRONTEND), name="static")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.update(SECURITY_HEADERS)
    if not request.url.path.startswith(("/docs", "/redoc", "/openapi")):  # Swagger UI loads scripts from a CDN
        response.headers["Content-Security-Policy"] = CSP
    return response


@app.get("/", include_in_schema=False)
def index():
    return FileResponse(FRONTEND / "index.html")


@app.api_route("/health", methods=["GET", "HEAD"], include_in_schema=False)
def health():
    """Keep-alive ping target: no DB, no LLM — costs nothing and never touches the Gemini quota.
    HEAD is allowed because uptime monitors often ping with HEAD."""
    return {"status": "ok"}


def _sample_title(text: str) -> str:
    first = next((l.strip() for l in text.splitlines() if l.strip() and not l.startswith("[")), "Nümunə")
    return first.replace("İ", "i").replace("I", "ı").lower().capitalize()


def _sample_files() -> dict[str, Path]:
    return {p.name: p for p in sorted(SAMPLES.iterdir()) if p.suffix.lower() in (".txt", ".docx", ".pdf")}


@app.get("/samples")
def list_samples():
    out = []
    for name, p in _sample_files().items():
        text = extract_text(name, p.read_bytes())
        out.append({
            "name": name,
            "format": p.suffix.lstrip(".").upper(),
            "title": _sample_title(text),
            "clauses": len(split_clauses(text)[1]),
        })
    return out


@app.get("/samples/{name}")
def get_sample(name: str):
    # Only names from the listing are allowed — no path traversal.
    path = _sample_files().get(name)
    if path is None:
        raise HTTPException(404, "Nümunə tapılmadı")
    return FileResponse(path, filename=name)


@app.get("/eval")
def eval_results():
    """Offline evaluation results (eval/*.py writes them; committed with the code) for the results page."""
    def read(name):
        p = EVAL / name
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None
    return {"retrieval": read("retrieval_results.json"), "risk": read("results.json")}


def _laws_for(db, a: Analysis) -> list[LawOut]:
    ids = {r for c in a.clauses for r in (c.law_refs or [])}
    rows = db.scalars(select(LawArticle).where(LawArticle.id.in_(ids))).all() if ids else []
    return [LawOut.model_validate(r) for r in sorted(rows, key=lambda r: int(r.id))]


def _load(db, public_id: str) -> Analysis:
    a = db.scalar(
        select(Analysis).where(Analysis.public_id == public_id).options(selectinload(Analysis.clauses))
    )
    if a is None:
        raise HTTPException(404, "Analiz tapılmadı")
    return a


def _run_pipeline(analysis_id: int, filename: str, data: bytes) -> None:
    """Runs in the background so the UI can poll status."""
    with SessionLocal() as db:
        a = db.get(Analysis, analysis_id)
        try:
            a.status = "parsing"
            db.commit()
            t0 = time.perf_counter()
            text = extract_text(filename, data)
            if len(text) > settings.max_chars:  # refuse rather than silently analyse half a contract
                raise ParseError(f"Müqavilə çox uzundur ({len(text):,} simvol). Maksimum {settings.max_chars:,} "
                                 "simvol dəstəklənir.".replace(",", " "))
            preamble, clauses = split_clauses(text)
            if not clauses:
                raise ParseError("Müqavilədə bənd tapılmadı.")
            if len(clauses) > settings.max_clauses:
                raise ParseError(f"Müqavilədə {len(clauses)} bənd var; maksimum {settings.max_clauses} dəstəklənir.")
            parse_ms = int((time.perf_counter() - t0) * 1000)
            a.preamble = preamble
            a.clauses = [ClauseRow(idx=c.idx, label=c.label or None, text=c.text) for c in clauses]
            a.status = "analyzing"
            db.commit()

            t0 = time.perf_counter()
            try:
                ctx = build_context(db, clauses)
            except Exception as e:  # retrieval is an enhancement: analyse without citations rather than fail
                print(f"[analysis {analysis_id}] law retrieval failed: {e!r}")
                ctx = None
            retrieval_ms = int((time.perf_counter() - t0) * 1000)
            result, metrics = analyze_clauses(clauses, ctx)
            by_idx = {r.clause_index: r for r in result.assessments}
            for row in a.clauses:
                r = by_idx[row.idx]
                row.risk, row.category = r.risk, r.category
                row.explanation, row.suggestion = r.explanation, r.suggestion or None
                row.law_refs = r.law_refs
                row.law_candidates = ctx.candidates.get(row.idx) if ctx else None
            a.summary = result.summary
            a.model, a.cost_usd, a.latency_ms = metrics["model"], metrics["cost_usd"], metrics["latency_ms"]
            a.invalid_refs = metrics.get("invalid_refs")
            a.trace = {
                "parse_ms": parse_ms, "retrieval_ms": retrieval_ms, "llm_ms": metrics.get("latency_ms"),
                "input_tokens": metrics.get("input_tokens"), "output_tokens": metrics.get("output_tokens"),
                "retrieval_mode": ctx.mode if ctx else None, "embed_model": current_model() if ctx else None,
                "law_corpus": ctx.corpus if ctx else 0, "law_in_prompt": len(ctx.articles) if ctx else 0,
            }
            a.status = "done"
        except (ParseError, AnalysisError) as e:
            a.status, a.error = "failed", str(e)
        except Exception as e:  # unexpected: keep the UI informative, keep details in logs
            a.status, a.error = "failed", "Gözlənilməz xəta baş verdi."
            print(f"[analysis {analysis_id}] {e!r}")
        db.commit()


@app.post("/analyses", response_model=AnalysisOut, status_code=202)
async def create_analysis(
    request: Request,
    background: BackgroundTasks,
    file: UploadFile | None = None,
    text: str | None = Form(default=None),
):
    # Every analysis is a paid / quota-limited LLM call: limit per client and for the whole service.
    if wait := limiter.check(client_ip(request, settings.trust_proxy)):
        raise HTTPException(429, f"Çox sayda analiz göndərdiniz. {wait // 60 + 1} dəqiqə sonra yenidən cəhd edin.",
                            headers={"Retry-After": str(wait)})
    with SessionLocal() as db:
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        if db.scalar(select(func.count(Analysis.id)).where(Analysis.created_at >= today)) >= settings.daily_analysis_limit:
            raise HTTPException(429, "Bugünkü analiz limiti dolub. Sabah yenidən cəhd edin.")

    max_bytes = settings.max_upload_mb * 1024 * 1024
    if file is not None:
        data, filename = await file.read(max_bytes + 1), (file.filename or "upload.txt")[:200]
    elif text and text.strip():
        data, filename = text.encode("utf-8"), "yapışdırılmış_mətn.txt"
    else:
        raise HTTPException(400, "Fayl yükləyin və ya mətn yapışdırın.")
    if len(data) > max_bytes:
        raise HTTPException(413, f"Fayl {settings.max_upload_mb} MB-dan böyük ola bilməz.")
    if problem := check_upload(filename, data):
        raise HTTPException(415, problem)

    with SessionLocal() as db:
        purge_expired(db)
        a = Analysis(filename=filename)
        db.add(a)
        db.commit()
        out = AnalysisOut.model_validate(_load(db, a.public_id))
        internal_id = a.id
    background.add_task(_run_pipeline, internal_id, filename, data)
    return out


@app.get("/analyses", response_model=list[AnalysisOut])
def list_analyses(ids: str = ""):
    """History of THIS browser only: the client sends the ids it created. There is no global listing."""
    wanted = [i for i in ids.split(",") if i][:50]
    if not wanted:
        return []
    with SessionLocal() as db:
        rows = db.scalars(
            select(Analysis).where(Analysis.public_id.in_(wanted)).order_by(Analysis.created_at.desc())
        ).all()
        return [AnalysisOut.model_validate(r).model_copy(update={"clauses": []}) for r in rows]


@app.get("/analyses/{public_id}", response_model=AnalysisOut)
def get_analysis(public_id: str):
    with SessionLocal() as db:
        a = _load(db, public_id)
        return AnalysisOut.model_validate(a).model_copy(update={"laws": _laws_for(db, a)})


@app.delete("/analyses/{public_id}", status_code=204)
def delete_analysis(public_id: str):
    with SessionLocal() as db:
        db.delete(_load(db, public_id))  # clauses go with it (cascade)
        db.commit()
    return Response(status_code=204)


@app.patch("/analyses/{public_id}/clauses/{clause_id}", response_model=ClauseOut)
def set_decision(public_id: str, clause_id: int, body: DecisionIn):
    with SessionLocal() as db:
        a = _load(db, public_id)
        row = next((c for c in a.clauses if c.id == clause_id), None)  # only clauses of THIS analysis
        if row is None:
            raise HTTPException(404, "Bənd tapılmadı")
        if body.decision == "edited" and not (body.user_text and body.user_text.strip()):
            raise HTTPException(400, "Redaktə üçün mətn boş ola bilməz.")
        row.decision = body.decision
        row.user_text = body.user_text if body.decision == "edited" else None
        db.commit()
        return ClauseOut.model_validate(row)


@app.get("/analyses/{public_id}/report.md", response_class=PlainTextResponse)
def export_report(public_id: str):
    with SessionLocal() as db:
        a = _load(db, public_id)
        if a.status != "done":
            raise HTTPException(409, "Analiz hələ bitməyib.")
        return build_report(a, _laws_for(db, a))


@app.get("/analyses/{public_id}/message", response_class=PlainTextResponse)
def negotiation_message(public_id: str):
    with SessionLocal() as db:
        a = _load(db, public_id)
        if a.status != "done":
            raise HTTPException(409, "Analiz hələ bitməyib.")
        return build_message(a)
