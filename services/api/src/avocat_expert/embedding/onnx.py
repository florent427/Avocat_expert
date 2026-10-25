"""Calcul local des embeddings (ONNX Runtime, processeur) : aucune donnée ne
quitte l'infrastructure.

Procédure de la fiche du modèle : préfixe de rôle, troncature à la longueur
maximale, mise en commun des états cachés (moyenne pondérée par le masque
d'attention, ou premier jeton), normalisation L2.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer

from avocat_expert.embedding.models import ModelFile, ModelSpec


class ModelIntegrityError(RuntimeError):
    pass


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_file(directory: Path, expected: ModelFile) -> Path:
    path = directory / expected.local_name
    if not path.is_file():
        raise ModelIntegrityError(f"fichier du modèle absent : {path}")
    actual = file_sha256(path)
    if actual != expected.sha256:
        raise ModelIntegrityError(f"empreinte inattendue pour {path} : {actual} (attendu {expected.sha256})")
    return path


class OnnxEmbedder:
    def __init__(self, spec: ModelSpec, directory: Path, *, threads: int | None = None, batch_size: int = 8) -> None:
        self.spec = spec
        self._batch_size = batch_size
        for expected in spec.files:  # graphe, données externes éventuelles, tokenizer
            verify_file(directory, expected)
        tokenizer = Tokenizer.from_file(str(directory / spec.tokenizer.local_name))
        tokenizer.enable_truncation(max_length=spec.max_tokens)
        self._tokenizer = tokenizer
        options = ort.SessionOptions()
        options.intra_op_num_threads = threads or os.cpu_count() or 1
        self._session = ort.InferenceSession(
            str(directory / spec.onnx.local_name), options, providers=["CPUExecutionProvider"]
        )
        self._inputs = {i.name for i in self._session.get_inputs()}
        # États cachés par jeton : premier tenseur de sortie de rang 3.
        self._output = next(o.name for o in self._session.get_outputs() if len(o.shape) == 3)

    @property
    def dimension(self) -> int:
        return self.spec.dimension

    def embed_queries(self, texts: list[str]) -> np.ndarray[Any, np.dtype[np.float32]]:
        return self._embed([self.spec.query_prefix + t for t in texts])

    def embed_passages(self, texts: list[str]) -> np.ndarray[Any, np.dtype[np.float32]]:
        return self._embed([self.spec.passage_prefix + t for t in texts])

    def _embed(self, texts: list[str]) -> np.ndarray[Any, np.dtype[np.float32]]:
        out = np.zeros((len(texts), self.spec.dimension), dtype=np.float32)
        encodings = self._tokenizer.encode_batch(texts)
        # Lots de longueurs voisines : le remplissage (et le calcul perdu) est minimal.
        order = sorted(range(len(texts)), key=lambda i: len(encodings[i].ids))
        for start in range(0, len(order), self._batch_size):
            chunk = order[start : start + self._batch_size]
            width = max(len(encodings[i].ids) for i in chunk)
            ids = np.zeros((len(chunk), width), dtype=np.int64)
            mask = np.zeros((len(chunk), width), dtype=np.int64)
            for row, i in enumerate(chunk):
                n = len(encodings[i].ids)
                ids[row, :n] = encodings[i].ids
                mask[row, :n] = 1
            feeds = {"input_ids": ids, "attention_mask": mask}
            if "token_type_ids" in self._inputs:
                feeds["token_type_ids"] = np.zeros_like(ids)
            (hidden,) = self._session.run([self._output], feeds)
            if self.spec.pooling == "cls":
                pooled = hidden[:, 0, :]
            else:
                weights = mask[..., None].astype(np.float32)
                pooled = (hidden * weights).sum(axis=1) / weights.sum(axis=1)
            pooled /= np.linalg.norm(pooled, axis=1, keepdims=True)
            out[chunk] = pooled
        return out
