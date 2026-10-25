"""Modèles d'embeddings auto-hébergés pris en charge (ADR 0017).

Chaque modèle est épinglé : dépôt, révision (commit) et empreinte SHA-256 de
chaque fichier, vérifiées au téléchargement et au chargement. Seuls des
fichiers de données sont chargés (graphe ONNX, tokenizer JSON) : ni
sérialisation pickle, ni code fourni par le dépôt du modèle.

Caractéristiques relevées sur les fiches des modèles (Hugging Face, consultées
le 2026-10-25) : licence, dimension, mise en commun (``1_Pooling/config.json``),
préfixes exigés à l'entraînement, longueur maximale. Empreintes : celles
publiées par Hugging Face (``X-Linked-Etag``), recalculées après téléchargement.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelFile:
    #: Chemin dans le dépôt du modèle, nom local après téléchargement.
    remote_path: str
    local_name: str
    sha256: str
    size: int


@dataclass(frozen=True)
class ModelSpec:
    key: str
    repository: str
    revision: str
    license: str
    dimension: int
    max_tokens: int
    query_prefix: str
    passage_prefix: str
    files: tuple[ModelFile, ...]
    #: Mise en commun des états cachés : moyenne pondérée par le masque.
    pooling: str = "mean"

    @property
    def onnx(self) -> ModelFile:
        return next(f for f in self.files if f.local_name == "model.onnx")

    @property
    def tokenizer(self) -> ModelFile:
        return next(f for f in self.files if f.local_name == "tokenizer.json")


MULTILINGUAL_E5_SMALL = ModelSpec(
    key="multilingual-e5-small@614241f6",
    repository="intfloat/multilingual-e5-small",
    revision="614241f622f53c4eeff9890bdc4f31cfecc418b3",
    license="MIT",
    dimension=384,
    max_tokens=512,
    query_prefix="query: ",
    passage_prefix="passage: ",
    files=(
        ModelFile(
            "onnx/model.onnx",
            "model.onnx",
            "ca456c06b3a9505ddfd9131408916dd79290368331e7d76bb621f1cba6bc8665",
            470268510,
        ),
        ModelFile(
            "onnx/tokenizer.json",
            "tokenizer.json",
            "0b44a9d7b51c3c62626640cda0e2c2f70fdacdc25bbbd68038369d14ebdf4c39",
            17082730,
        ),
    ),
)

MULTILINGUAL_E5_BASE = ModelSpec(
    key="multilingual-e5-base@d1287505",
    repository="intfloat/multilingual-e5-base",
    revision="d128750597153bb5987e10b1c3493a34e5a4502a",
    license="MIT",
    dimension=768,
    max_tokens=512,
    query_prefix="query: ",
    passage_prefix="passage: ",
    files=(
        ModelFile(
            "onnx/model.onnx",
            "model.onnx",
            "84a4d426f7e87a6bf5bf195f0bae2c4a7d15f675b23ca96f42fab8326d7a77aa",
            1110059084,
        ),
        ModelFile(
            "onnx/tokenizer.json",
            "tokenizer.json",
            "62c24cdc13d4c9952d63718d6c9fa4c287974249e16b7ade6d5a85e7bbb75626",
            17082660,
        ),
    ),
)

MODELS: dict[str, ModelSpec] = {spec.key: spec for spec in (MULTILINGUAL_E5_SMALL, MULTILINGUAL_E5_BASE)}


def model_spec(key: str) -> ModelSpec:
    try:
        return MODELS[key]
    except KeyError:
        raise ValueError(f"modèle d'embeddings inconnu : {key!r} (pris en charge : {', '.join(MODELS)})") from None
