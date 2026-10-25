"""Embeddings auto-hébergés du corpus (SRCH-02, ADR 0017)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from avocat_expert.config import Settings
    from avocat_expert.embedding.onnx import OnnxEmbedder


@lru_cache(maxsize=2)
def _load(key: str, directory: str, threads: int) -> OnnxEmbedder:
    from avocat_expert.embedding.models import model_spec
    from avocat_expert.embedding.onnx import OnnxEmbedder

    return OnnxEmbedder(model_spec(key), Path(directory), threads=threads or None)


def configured_embedder(settings: Settings) -> OnnxEmbedder | None:
    """Modèle configuré, chargé une fois par processus (vérification des
    empreintes et chargement : environ 5 s) ; ``None`` si le canal est désactivé."""
    if not settings.embedding_model:
        return None
    if not settings.embedding_model_dir:
        raise ValueError("AVX_EMBEDDING_MODEL défini sans AVX_EMBEDDING_MODEL_DIR")
    return _load(settings.embedding_model, settings.embedding_model_dir, settings.embedding_threads)
