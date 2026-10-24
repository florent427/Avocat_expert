"""Livraisons LEGI publiées par la DILA : inventaire, plan d'application, téléchargement.

Vérifié sur l'index réel https://echanges.dila.gouv.fr/OPENDATA/LEGI/ (2026-10-24) :
un stock ``Freemium_legi_global_AAAAMMJJ-HHMMSS.tar.gz`` et des livraisons
incrémentales ``LEGI_AAAAMMJJ-HHMMSS.tar.gz``, dont certaines antérieures au
stock. Fiche DILA LEGI (24/08/2017) : utiliser le dernier stock pour une
première intégration ; documentation XML (2018) : appliquer les livraisons
dans l'ordre croissant.

Sortie réseau limitée à l'hôte officiel, en HTTPS, avec taille maximale.
"""

from __future__ import annotations

import hashlib
import re
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from avocat_expert.connectors.legi.archive import archive_timestamp, is_stock

BASE_URL = "https://echanges.dila.gouv.fr/OPENDATA/LEGI/"
ALLOWED_HOST = "echanges.dila.gouv.fr"
MAX_INDEX_BYTES = 2 * 1024 * 1024
MAX_ARCHIVE_BYTES = 4 * 1024 * 1024 * 1024
_HREF = re.compile(r'href="((?:LEGI|Freemium_legi_global)_\d{8}-\d{6}\.tar\.gz)"')


class RemoteError(RuntimeError):
    pass


@dataclass(frozen=True, order=True)
class RemoteArchive:
    timestamp: datetime
    name: str

    @property
    def is_stock(self) -> bool:
        return is_stock(self.name)


def parse_index(html: str) -> list[RemoteArchive]:
    """Archives listées par l'index du répertoire, triées par horodatage."""
    archives = set()
    for name in _HREF.findall(html):
        stamp = archive_timestamp(name)
        if stamp is not None:
            archives.add(RemoteArchive(stamp, name))
    return sorted(archives)


def plan(available: list[RemoteArchive], last_applied: datetime | None) -> list[RemoteArchive]:
    """Livraisons à appliquer, dans l'ordre.

    * aucune livraison intégrée : dernier stock, puis les livraisons
      incrémentales qui lui sont postérieures ;
    * sinon : livraisons incrémentales postérieures à la dernière intégrée
      (un stock plus récent n'est pas réappliqué : il ne remplace pas
      l'historique déjà constitué).
    """
    deltas = sorted(a for a in available if not a.is_stock)
    if last_applied is None:
        stocks = sorted(a for a in available if a.is_stock)
        if not stocks:
            raise RemoteError("aucun stock disponible : première intégration impossible")
        stock = stocks[-1]
        return [stock, *(d for d in deltas if d.timestamp > stock.timestamp)]
    return [d for d in deltas if d.timestamp > last_applied]


def _checked(url: str) -> str:
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.hostname != ALLOWED_HOST:
        raise RemoteError(f"URL hors du périmètre autorisé : {url}")
    return url


class _SameHostRedirects(urllib.request.HTTPRedirectHandler):
    """Refuse toute redirection hors de l'hôte autorisé."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        _checked(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_OPENER = urllib.request.build_opener(_SameHostRedirects)


def fetch_index(base_url: str = BASE_URL, timeout: float = 30.0) -> list[RemoteArchive]:
    with _OPENER.open(_checked(base_url), timeout=timeout) as response:
        raw = response.read(MAX_INDEX_BYTES + 1)
    if len(raw) > MAX_INDEX_BYTES:
        raise RemoteError("index anormalement volumineux")
    return parse_index(raw.decode("utf-8", errors="replace"))


def download(archive: RemoteArchive, directory: Path, base_url: str = BASE_URL, timeout: float = 60.0) -> Path:
    """Télécharge l'archive (fichier temporaire puis renommage) ; réutilise un
    fichier déjà complet. Renvoie le chemin local."""
    target = directory / archive.name
    if target.is_file():
        return target
    directory.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(target.suffix + ".partiel")
    url = _checked(urljoin(base_url, archive.name))
    size = 0
    with _OPENER.open(url, timeout=timeout) as response, partial.open("wb") as out:
        for chunk in iter(lambda: response.read(1 << 20), b""):
            size += len(chunk)
            if size > MAX_ARCHIVE_BYTES:
                raise RemoteError(f"archive {archive.name} au-delà de la taille maximale")
            out.write(chunk)
    partial.rename(target)
    return target


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


@dataclass(frozen=True)
class Freshness:
    """Écart entre le corpus et les livraisons publiées (ING-10)."""

    last_applied: datetime | None
    latest_published: datetime | None
    pending: tuple[str, ...]
    lag_days: float | None

    @property
    def up_to_date(self) -> bool:
        return self.last_applied is not None and not self.pending

    def as_dict(self) -> dict[str, object]:
        return {
            "derniere_livraison_integree": None if self.last_applied is None else self.last_applied.isoformat(),
            "derniere_livraison_publiee": None if self.latest_published is None else self.latest_published.isoformat(),
            "livraisons_en_attente": len(self.pending),
            "premiere_en_attente": self.pending[0] if self.pending else None,
            "retard_jours": self.lag_days,
            "a_jour": self.up_to_date,
        }


def freshness(available: list[RemoteArchive], last_applied: datetime | None) -> Freshness:
    pending = plan(available, last_applied)
    latest = max((a.timestamp for a in available), default=None)
    lag = None
    if latest is not None and last_applied is not None:
        lag = round(max((latest - last_applied).total_seconds(), 0) / 86400, 2)
    return Freshness(last_applied, latest, tuple(a.name for a in pending), lag)
