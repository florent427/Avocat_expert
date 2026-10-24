"""Lecture d'une archive LEGI (``.tar.gz``) ou d'un répertoire déjà extrait.

L'archive est lue **en flux** (``r|gz``) : jamais extraite sur disque ni
chargée en mémoire, ce qui écarte les attaques par traversée de chemin et
permet de traiter le stock complet (1,1 Go compressé). Seuls les fichiers
réguliers sont lus, avec une taille maximale par membre. L'ordre de lecture
est celui de l'archive (répertoire : ordre lexicographique des chemins), ce
qui rend la reprise après incident déterministe.
"""

from __future__ import annotations

import re
import tarfile
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

MAX_MEMBER_BYTES = 20 * 1024 * 1024
_SUPPRESSION_FILE = "liste_suppression_legi.dat"
_ID_IN_LINE = re.compile(r"(LEGI[A-Z]{4}\d{12})\s*$")
_ARCHIVE_NAME = re.compile(r"^(?:LEGI|Freemium_legi_global)_(\d{8}-\d{6})(?:\.tar\.gz)?$")

EntryKind = Literal["ARTICLE", "TEXT_VERSION", "TEXT_STRUCT", "SECTION"]
_KINDS: tuple[tuple[re.Pattern[str], EntryKind], ...] = (
    (re.compile(r"/article/(?:.+/)?LEGIARTI\d{12}\.xml$"), "ARTICLE"),
    (re.compile(r"/texte/version/(?:.+/)?LEGITEXT\d{12}\.xml$"), "TEXT_VERSION"),
    (re.compile(r"/texte/struct/(?:.+/)?LEGITEXT\d{12}\.xml$"), "TEXT_STRUCT"),
    (re.compile(r"/section_ta/(?:.+/)?LEGISCTA\d{12}\.xml$"), "SECTION"),
)


def archive_timestamp(name: str) -> datetime | None:
    """Horodatage d'une livraison DILA d'après son nom (``LEGI_AAAAMMJJ-HHMMSS.tar.gz``
    ou ``Freemium_legi_global_AAAAMMJJ-HHMMSS.tar.gz``) ; ``None`` si le nom ne suit
    pas cette forme. Le fuseau n'est pas documenté par la DILA."""
    match = _ARCHIVE_NAME.match(name)
    if match is None:
        return None
    try:
        return datetime.strptime(match.group(1), "%Y%m%d-%H%M%S")
    except ValueError:
        return None


def is_stock(name: str) -> bool:
    return name.startswith("Freemium_legi_global_")


@dataclass(frozen=True)
class ArchiveEntry:
    path: str
    data: bytes
    kind: EntryKind = "ARTICLE"


@dataclass(frozen=True)
class Withdrawal:
    official_id: str
    raw_entry: str


@dataclass
class ArchiveReader:
    """Parcours unique d'une livraison : fichiers XML classés par nature et
    liste de suppression, collectée au passage (``withdrawals``)."""

    location: Path
    withdrawals: list[Withdrawal]
    ignored: int = 0
    eli_index: int = 0
    oversized: int = 0

    def __init__(self, location: Path) -> None:
        self.location = location
        self.withdrawals = []

    def _skip(self, path: str) -> None:
        # Index ELI (legi/global/eli/…/versions.xml) : correspondances entre
        # identifiants ELI et versions, sans contenu juridique propre.
        if "/eli/" in path:
            self.eli_index += 1
        else:
            self.ignored += 1

    def entries(self) -> Iterator[ArchiveEntry]:
        if self.location.is_dir():
            yield from self._from_directory()
        else:
            yield from self._from_tar()

    def _classify(self, path: str) -> EntryKind | None:
        for pattern, kind in _KINDS:
            if pattern.search(path):
                return kind
        return None

    def _from_directory(self) -> Iterator[ArchiveEntry]:
        for file in sorted(self.location.rglob("*")):
            if not file.is_file() or file.is_symlink():
                continue
            relative = _relative(file.relative_to(self.location).as_posix())
            if file.name == _SUPPRESSION_FILE:
                self.withdrawals.extend(_parse_withdrawals(file.read_text("utf-8")))
                continue
            kind = self._classify("/" + relative)
            if kind is None:
                self._skip("/" + relative)
            elif file.stat().st_size > MAX_MEMBER_BYTES:
                self.oversized += 1
            else:
                yield ArchiveEntry(relative, file.read_bytes(), kind)

    def _from_tar(self) -> Iterator[ArchiveEntry]:
        with tarfile.open(self.location, mode="r|gz") as archive:
            for member in archive:
                # tarfile conserve chaque TarInfo lu, y compris en flux : sans
                # purge, la mémoire croît avec le nombre de membres (plus de
                # 3 Go constatés sur le stock complet).
                archive.members.clear()  # type: ignore[attr-defined]
                if not member.isreg():
                    continue
                if member.size > MAX_MEMBER_BYTES:
                    self.oversized += 1
                    continue
                if member.name.endswith(_SUPPRESSION_FILE):
                    handle = archive.extractfile(member)
                    if handle is not None:
                        self.withdrawals.extend(_parse_withdrawals(handle.read().decode("utf-8")))
                    continue
                relative = _relative(member.name)
                kind = self._classify("/" + relative)
                if kind is None:
                    self._skip("/" + relative)
                    continue
                handle = archive.extractfile(member)
                if handle is not None:
                    yield ArchiveEntry(relative, handle.read(), kind)


def _relative(path: str) -> str:
    # Les chemins sont conservés relativement à la racine « legi/ » de l'archive.
    index = path.find("legi/")
    return path[index:] if index >= 0 else path


def iter_article_files(location: Path) -> Iterator[ArchiveEntry]:
    """Fichiers article seulement (outils et tests)."""
    return (e for e in ArchiveReader(location).entries() if e.kind == "ARTICLE")


def _parse_withdrawals(raw: str) -> list[Withdrawal]:
    result = []
    for line in raw.splitlines():
        line = line.strip()
        match = _ID_IN_LINE.search(line)
        if match:
            result.append(Withdrawal(official_id=match.group(1), raw_entry=line))
    return result


def read_withdrawals(location: Path) -> list[Withdrawal]:
    """Liste de suppression publiée avec chaque archive incrémentale."""
    reader = ArchiveReader(location)
    for _ in reader.entries():
        pass
    return reader.withdrawals
