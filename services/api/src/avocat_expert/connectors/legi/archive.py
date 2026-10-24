"""Lecture d'une archive LEGI (``.tar.gz``) ou d'un répertoire déjà extrait.

L'archive n'est jamais extraite sur disque : les membres sont lus en mémoire,
ce qui écarte les attaques par traversée de chemin. Seuls les fichiers
réguliers sont lus, avec une taille maximale par membre.
"""

from __future__ import annotations

import re
import tarfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

MAX_MEMBER_BYTES = 20 * 1024 * 1024
_ARTICLE_FILE = re.compile(r"(^|/)LEGIARTI\d{12}\.xml$")
_SUPPRESSION_FILE = "liste_suppression_legi.dat"
_ID_IN_LINE = re.compile(r"(LEGI[A-Z]{4}\d{12})\s*$")


@dataclass(frozen=True)
class ArchiveEntry:
    path: str
    data: bytes


@dataclass(frozen=True)
class Withdrawal:
    official_id: str
    raw_entry: str


def _relative(path: str) -> str:
    # Les chemins sont conservés relativement à la racine « legi/ » de l'archive.
    index = path.find("legi/")
    return path[index:] if index >= 0 else path


def iter_article_files(location: Path) -> Iterator[ArchiveEntry]:
    if location.is_dir():
        for file in sorted(location.rglob("LEGIARTI*.xml")):
            if file.is_file() and not file.is_symlink() and file.stat().st_size <= MAX_MEMBER_BYTES:
                yield ArchiveEntry(_relative(file.relative_to(location).as_posix()), file.read_bytes())
        return
    with tarfile.open(location, mode="r:gz") as archive:
        for member in archive:
            if not member.isreg() or not _ARTICLE_FILE.search(member.name):
                continue
            if member.size > MAX_MEMBER_BYTES:
                continue
            handle = archive.extractfile(member)
            if handle is not None:
                yield ArchiveEntry(_relative(member.name), handle.read())


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
    if location.is_dir():
        files = [f for f in location.rglob(_SUPPRESSION_FILE) if f.is_file() and not f.is_symlink()]
        return [w for f in sorted(files) for w in _parse_withdrawals(f.read_text("utf-8"))]
    with tarfile.open(location, mode="r:gz") as archive:
        for member in archive:
            if member.isreg() and member.name.endswith(_SUPPRESSION_FILE) and member.size <= MAX_MEMBER_BYTES:
                handle = archive.extractfile(member)
                if handle is not None:
                    return _parse_withdrawals(handle.read().decode("utf-8"))
    return []
