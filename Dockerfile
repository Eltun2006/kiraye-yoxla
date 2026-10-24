# KirayəYoxla — image for Hugging Face Spaces (Docker SDK). Secrets (GEMINI_API_KEY, DATABASE_URL) come from the
# Space settings at runtime and are never baked into the image.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# Spaces run the container as uid 1000
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    HF_HOME=/home/user/.cache/huggingface
WORKDIR /home/user/app

# CPU-only torch first (the default wheel bundles CUDA: ~2.5 GB more), then the rest
RUN pip install --user torch --index-url https://download.pytorch.org/whl/cpu
COPY --chown=user requirements.txt .
RUN pip install --user -r requirements.txt

# Bake the embedding model into the image: no 1 GB download on every cold start
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('intfloat/multilingual-e5-base')"

COPY --chown=user . .

# Behind the Spaces proxy; on first start an empty law table is filled from data/law
ENV TRUST_PROXY=true \
    AUTO_INGEST_LAW=true \
    LLM_PROVIDER=gemini

EXPOSE 7860
# One worker: the rate limiter lives in process memory
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "7860"]
