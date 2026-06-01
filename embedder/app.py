"""AssayLens embedding microservice.

A tiny FastAPI wrapper around a sentence-transformers model so the knowledge
indexer and the agent's semantic search share ONE copy of the model (rather
than pulling torch into both images). Returns L2-normalized vectors, so cosine
similarity == dot product downstream in Elasticsearch kNN.
"""
from __future__ import annotations

import os

from fastapi import FastAPI
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer

MODEL_NAME = os.getenv("EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
_model = SentenceTransformer(MODEL_NAME)
DIM = _model.get_sentence_embedding_dimension()

app = FastAPI(title="AssayLens Embedder", version="0.1.0")


class EmbedRequest(BaseModel):
    texts: list[str]


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "model": MODEL_NAME, "dim": DIM}


@app.post("/embed")
def embed(req: EmbedRequest) -> dict:
    vecs = _model.encode(
        req.texts, normalize_embeddings=True, convert_to_numpy=True, batch_size=64
    )
    return {"model": MODEL_NAME, "dim": DIM, "vectors": [v.tolist() for v in vecs]}
