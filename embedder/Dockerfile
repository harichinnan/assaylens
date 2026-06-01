# =============================================================================
# AssayLens embedding service: sentence-transformers (all-MiniLM-L6-v2, 384-dim).
# The model is baked into the image at build time so startup is fast and offline.
# =============================================================================
FROM python:3.11-slim

ENV HF_HOME=/models \
    SENTENCE_TRANSFORMERS_HOME=/models \
    TRANSFORMERS_OFFLINE=0

# One resolution so numpy stays <2: torch 2.2.2 is built against numpy 1.x and
# raises "Numpy is not available" at .numpy() if numpy 2.x is present. Pinning
# torch 2.2.2 (CPU) also avoids the nvidia-* CUDA wheels newer torch pulls.
RUN pip install --no-cache-dir \
      "numpy<2" "torch==2.2.2" \
      "fastapi==0.111.0" "uvicorn[standard]==0.30.1" \
      "sentence-transformers==3.0.1"

ARG EMBED_MODEL=sentence-transformers/all-MiniLM-L6-v2
ENV EMBED_MODEL=${EMBED_MODEL}
# Pre-download the model into the image.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('${EMBED_MODEL}')"

WORKDIR /app
COPY app.py /app/app.py

EXPOSE 8100
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8100"]
