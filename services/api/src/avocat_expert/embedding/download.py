"""Téléchargement des fichiers d'un modèle épinglé (opération d'exploitation,
jamais à l'exécution de l'API).

Sortie réseau : HTTPS vers ``huggingface.co`` et son réseau de distribution
(``*.hf.co``, cible des redirections constatée le 2026-10-25). L'intégrité ne
dépend pas de l'hôte : chaque fichier est refusé si son empreinte SHA-256
diffère de celle épinglée dans ``models.py``.
"""

from __future__ import annotations

import urllib.request
from pathlib import Path
from urllib.parse import quote, urlsplit

from avocat_expert.embedding.models import ModelSpec
from avocat_expert.embedding.onnx import ModelIntegrityError, file_sha256


class DownloadError(RuntimeError):
    pass


def _checked(url: str) -> str:
    parts = urlsplit(url)
    host = parts.hostname or ""
    if parts.scheme != "https" or not (host == "huggingface.co" or host.endswith(".hf.co")):
        raise DownloadError(f"URL hors du périmètre autorisé : {parts.scheme}://{host}")
    return url


class _AllowedRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        _checked(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_OPENER = urllib.request.build_opener(_AllowedRedirects)


def file_url(spec: ModelSpec, remote_path: str) -> str:
    return f"https://huggingface.co/{spec.repository}/resolve/{spec.revision}/{quote(remote_path)}"


def download_model(spec: ModelSpec, directory: Path, timeout: float = 60.0) -> list[Path]:
    """Télécharge les fichiers absents ou altérés ; renvoie les chemins vérifiés."""
    directory.mkdir(parents=True, exist_ok=True)
    paths = []
    for expected in spec.files:
        target = directory / expected.local_name
        if target.is_file() and file_sha256(target) == expected.sha256:
            paths.append(target)
            continue
        partial = target.with_name(target.name + ".partiel")
        size = 0
        url = _checked(file_url(spec, expected.remote_path))
        with _OPENER.open(url, timeout=timeout) as response, partial.open("wb") as out:
            for chunk in iter(lambda: response.read(1 << 20), b""):
                size += len(chunk)
                if size > expected.size:
                    raise DownloadError(f"{expected.remote_path} : taille supérieure à {expected.size} octets")
                out.write(chunk)
        actual = file_sha256(partial)
        if actual != expected.sha256:
            partial.unlink()
            raise ModelIntegrityError(f"{expected.remote_path} : empreinte {actual}, attendue {expected.sha256}")
        partial.rename(target)
        paths.append(target)
    return paths
