"""Embeddings : calcul, conservation, index vectoriel et canal sémantique.

Un vectoriseur déterministe (sac de mots haché) remplace le modèle pour
éprouver la chaîne sans dépendre de ses fichiers ; le modèle réel est éprouvé
dans ``test_embedding_model.py``.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
import psycopg
import pytest

from avocat_expert.embedding.download import DownloadError, _checked, file_url
from avocat_expert.embedding.models import MULTILINGUAL_E5_SMALL, ModelFile, ModelSpec
from avocat_expert.embedding.onnx import ModelIntegrityError, verify_file
from avocat_expert.embedding.store import compute_missing, input_sha256, passage_text
from avocat_expert.search import indexer
from avocat_expert.search.opensearch import OpenSearchClient, OpenSearchSemanticSearcher
from avocat_expert.storage.corpus import CorpusRepository

DIMENSION = 32


def _spec() -> ModelSpec:
    return ModelSpec(
        key=f"test-{uuid.uuid4().hex[:8]}",
        repository="test/sac-de-mots",
        revision="0" * 40,
        license="test",
        dimension=DIMENSION,
        max_tokens=512,
        query_prefix="query: ",
        passage_prefix="passage: ",
        files=(),
    )


class HashedBagOfWords:
    def __init__(self, spec: ModelSpec) -> None:
        self.spec = spec
        self.calls = 0

    def _vector(self, text: str) -> np.ndarray[Any, np.dtype[np.float32]]:
        vector = np.zeros(DIMENSION, dtype=np.float32)
        for word in re.findall(r"\w{4,}", text.lower()):
            vector[int(hashlib.sha256(word.encode()).hexdigest(), 16) % DIMENSION] += 1.0
        norm = np.linalg.norm(vector)
        return vector / norm if norm else vector + 1.0 / np.sqrt(DIMENSION)

    def embed_passages(self, texts: list[str]) -> np.ndarray[Any, np.dtype[np.float32]]:
        self.calls += len(texts)
        return np.stack([self._vector(t) for t in texts]) if texts else np.zeros((0, DIMENSION), np.float32)

    def embed_queries(self, texts: list[str]) -> np.ndarray[Any, np.dtype[np.float32]]:
        return np.stack([self._vector(t) for t in texts])


# --- sans base ---------------------------------------------------------------


def test_passage_carries_context_and_hash_depends_on_exact_input() -> None:
    text = passage_text("Code du travail", ["Partie législative", "Chapitre II"], "L5422-2", "La durée…")
    assert text == "Code du travail > Partie législative > Chapitre II > Article L5422-2\nLa durée…"
    assert passage_text("Décret", [], None, "Texte") == "Décret\nTexte"
    spec = MULTILINGUAL_E5_SMALL
    assert input_sha256(spec, text) == hashlib.sha256(("passage: " + text).encode()).hexdigest()
    assert input_sha256(spec, text) != input_sha256(spec, text + " ")


def test_model_files_are_pinned_and_downloads_stay_on_the_model_host() -> None:
    spec = MULTILINGUAL_E5_SMALL
    assert re.fullmatch(r"[0-9a-f]{40}", spec.revision)
    assert all(re.fullmatch(r"[0-9a-f]{64}", f.sha256) for f in spec.files)
    assert {f.local_name for f in spec.files} == {"model.onnx", "tokenizer.json"}  # données, aucun code
    assert file_url(spec, "onnx/model.onnx").startswith(
        "https://huggingface.co/intfloat/multilingual-e5-small/resolve/614241f622f53c4eeff9890bdc4f31cfecc418b3/"
    )
    _checked("https://us.aws.cdn.hf.co/xet-bridge-us/abc")
    for url in ("http://huggingface.co/x", "https://huggingface.co.evil.example/x", "https://example.org/x"):
        with pytest.raises(DownloadError):
            _checked(url)


def test_altered_model_file_is_refused(tmp_path: Path) -> None:
    (tmp_path / "model.onnx").write_bytes(b"pas un modele")
    expected = ModelFile("onnx/model.onnx", "model.onnx", hashlib.sha256(b"autre").hexdigest(), 5)
    with pytest.raises(ModelIntegrityError, match="empreinte inattendue"):
        verify_file(tmp_path, expected)
    with pytest.raises(ModelIntegrityError, match="absent"):
        verify_file(tmp_path, ModelFile("onnx/x", "tokenizer.json", "0" * 64, 1))


# --- base PostgreSQL ------------------------------------------------------------


@pytest.mark.db
def test_compute_is_scoped_idempotent_and_reuses_identical_inputs(conn: psycopg.Connection[Any]) -> None:
    embedder = HashedBagOfWords(_spec())
    first = compute_missing(conn, embedder, documents=["LEGITEXT000006072050"], batch=7)
    in_scope = conn.execute(
        """SELECT count(*) FROM provision_version pv JOIN provision p ON p.id = pv.provision_id
           JOIN legal_document d ON d.id = p.document_id
           WHERE pv.sys_to IS NULL AND NOT pv.withdrawn_from_source AND d.official_id = 'LEGITEXT000006072050'"""
    ).fetchone()
    assert in_scope is not None and first.versions == in_scope[0] > 0
    assert first.computed + first.reused == first.versions
    stored = conn.execute(
        "SELECT count(*), count(DISTINCT input_sha256) FROM provision_embedding WHERE model_key = %s",
        (embedder.spec.key,),
    ).fetchone()
    assert stored == (first.versions, first.computed)
    # Reprise : rien à refaire.
    calls = embedder.calls
    again = compute_missing(conn, embedder, documents=["LEGITEXT000006072050"])
    assert again.versions == 0 and embedder.calls == calls
    # Périmètre par date et plafond : un autre modèle ne voit pas les vecteurs du premier.
    other = compute_missing(conn, HashedBagOfWords(_spec()), as_of=date(2026, 10, 24), limit=3)
    assert other.versions == 3


@pytest.mark.db
def test_vectors_are_insert_only(conn: psycopg.Connection[Any]) -> None:
    embedder = HashedBagOfWords(_spec())
    compute_missing(conn, embedder, limit=1)
    with pytest.raises(psycopg.errors.RaiseException, match="insertion seule"):
        conn.execute("DELETE FROM provision_embedding WHERE model_key = %s", (embedder.spec.key,))
    with pytest.raises(psycopg.errors.RaiseException, match="insertion seule"):
        conn.execute("UPDATE embedding_vector SET created_at = now() WHERE model_key = %s", (embedder.spec.key,))


@pytest.mark.db
def test_model_key_cannot_be_reused_with_other_characteristics(conn: psycopg.Connection[Any]) -> None:
    spec = _spec()
    compute_missing(conn, HashedBagOfWords(spec), limit=1)
    altered = ModelSpec(**{**spec.__dict__, "revision": "1" * 40})
    with pytest.raises(ValueError, match="autres caractéristiques"):
        compute_missing(conn, HashedBagOfWords(altered), limit=1)


# --- OpenSearch -----------------------------------------------------------------


@pytest.fixture
def alias(opensearch_url: str) -> Iterator[str]:
    name = f"avx-test-{uuid.uuid4().hex[:8]}"
    yield name
    client = OpenSearchClient(opensearch_url)
    for physical in client.request("GET", f"/_alias/{name}", ok_missing=True) or {}:
        client.request("DELETE", f"/{physical}", ok_missing=True)


@pytest.mark.db
@pytest.mark.search
def test_semantic_channel_follows_dates_scope_and_model(
    conn: psycopg.Connection[Any], opensearch_url: str, alias: str
) -> None:
    embedder = HashedBagOfWords(_spec())
    compute_missing(conn, embedder)
    client = OpenSearchClient(opensearch_url)
    indexer.rebuild(conn, client, alias, batch=10, embedding=embedder.spec)
    searcher = OpenSearchSemanticSearcher(client, alias, CorpusRepository(conn), embedder)
    assert searcher.enabled and "auto-hébergé" in searcher.detail

    question = "allocation d'assurance des travailleurs privés d'emploi"
    hits = searcher.search(question, date(2026, 10, 24), 5)
    assert "LEGIARTI000048590547" in [h.version.official_id for h in hits]  # L5422-1 en vigueur
    assert all(-1.0 <= h.score <= 1.0 for h in hits)
    assert [h.score for h in hits] == sorted((h.score for h in hits), reverse=True)
    in_2010 = [h.version.official_id for h in searcher.search(question, date(2010, 1, 1), 20)]
    assert "LEGIARTI000048590547" not in in_2010
    scoped = searcher.search(question, date(2026, 10, 24), 20, frozenset({"LEGITEXT000006073984"}))
    assert scoped and {h.version.document_official_id for h in scoped} == {"LEGITEXT000006073984"}
    for year in (1990, 2026, 2300):  # début non fixé : jamais retenu
        found = searcher.search("santé publique médicaments", date(year, 1, 1), 50)
        assert "LEGIARTI000025453562" not in [h.version.official_id for h in found]

    # Une requête n'est jamais vectorisée par un autre modèle que celui de l'index.
    other = OpenSearchSemanticSearcher(client, alias, CorpusRepository(conn), HashedBagOfWords(_spec()))
    assert not other.enabled and "reconstruction requise" in other.detail
    assert other.search(question, date(2026, 10, 24), 5) == []
    with pytest.raises(indexer.IndexModelMismatchError):
        indexer.update(conn, client, alias, embedding=None)


@pytest.mark.db
@pytest.mark.search
def test_incremental_update_adds_vectors_computed_later(
    conn: psycopg.Connection[Any], opensearch_url: str, alias: str
) -> None:
    embedder = HashedBagOfWords(_spec())
    client = OpenSearchClient(opensearch_url)
    indexer.rebuild(conn, client, alias, embedding=embedder.spec)  # aucun vecteur encore
    searcher = OpenSearchSemanticSearcher(client, alias, CorpusRepository(conn), embedder)
    assert searcher.search("allocation d'assurance", date(2026, 10, 24), 5) == []
    computed = compute_missing(conn, embedder, documents=["LEGITEXT000006072050"])
    report = indexer.update(conn, client, alias, embedding=embedder.spec)
    assert report.indexed == computed.versions
    hits = searcher.search("allocation d'assurance", date(2026, 10, 24), 5)
    assert hits and {h.version.document_official_id for h in hits} == {"LEGITEXT000006072050"}


# --- modèle réel ----------------------------------------------------------------


@pytest.mark.embedding
def test_real_model_vectors_are_normalised_and_independent_of_batching(embedding_model_dir: Path) -> None:
    from avocat_expert.embedding.models import MULTILINGUAL_E5_BASE
    from avocat_expert.embedding.onnx import OnnxEmbedder

    embedder = OnnxEmbedder(MULTILINGUAL_E5_BASE, embedding_model_dir, batch_size=2)
    texts = [
        "Code du travail > Article L5422-2\nLa durée d'indemnisation tient compte de l'âge des intéressés.",
        "Majorité",
        "Code civil > Article 414\nLa majorité est fixée à dix-huit ans accomplis.",
    ]
    together = embedder.embed_passages(texts)
    assert together.shape == (3, 768)
    assert np.allclose(np.linalg.norm(together, axis=1), 1.0, atol=1e-5)
    # Lots triés par longueur et complétés : chaque vecteur reste celui du texte seul.
    alone = np.stack([embedder.embed_passages([t])[0] for t in texts])
    assert np.allclose(together, alone, atol=1e-4)
    query = embedder.embed_queries(["Pendant combien de temps l'allocation chômage est-elle versée ?"])[0]
    assert float(query @ together[0]) > float(query @ together[2])
