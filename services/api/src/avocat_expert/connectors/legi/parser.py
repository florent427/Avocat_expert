"""Analyse d'un fichier article LEGI (``LEGIARTI*.xml``).

Le parseur est volontairement strict : un élément obligatoire absent lève
``LegiFormatError`` au lieu de produire une donnée partielle silencieuse.
"""

from __future__ import annotations

import hashlib
import re
from datetime import date
from xml.etree.ElementTree import Element

import defusedxml.ElementTree as SafeET
from pydantic import BaseModel, ConfigDict

from avocat_expert.domain.temporal import LegalPeriod

#: Valeur sentinelle observée dans LEGI pour « pas de date de fin ».
OPEN_END_SENTINEL = date(2999, 1, 1)

_ARTICLE_ID = re.compile(r"^LEGIARTI\d{12}$")
_BLOCK_TAGS = {"p", "div", "br", "tr", "li", "table", "blockquote"}


class LegiFormatError(ValueError):
    """Le fichier ne respecte pas le format LEGI attendu."""


class DeclaredVersion(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    official_id: str
    status: str
    raw_valid_from: str
    raw_valid_to: str | None
    number: str | None


class LegiLink(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    link_type: str
    direction: str | None
    target_official_id: str | None
    target_text_id: str | None
    target_label: str
    target_date: date | None


class LegiArticle(BaseModel):
    """Version d'article telle que publiée par la DILA."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    official_id: str
    number: str
    status: str
    raw_valid_from: str
    raw_valid_to: str | None
    period: LegalPeriod
    text_official_id: str
    text_nature: str
    text_title: str
    text_short_title: str | None
    section_path: tuple[str, ...]
    content: str
    content_sha256: str
    nota: str | None
    declared_versions: tuple[DeclaredVersion, ...]
    links: tuple[LegiLink, ...]
    source_path: str
    source_file_sha256: str


def _text_of(element: Element | None) -> str:
    """Texte d'un bloc XHTML en conservant les ruptures de paragraphe."""
    if element is None:
        return ""
    parts: list[str] = []

    def walk(node: Element) -> None:
        tag = node.tag.lower() if isinstance(node.tag, str) else ""
        if tag in _BLOCK_TAGS:
            parts.append("\n")
        if node.text:
            parts.append(node.text)
        for child in node:
            walk(child)
            if child.tail:
                parts.append(child.tail)
        if tag in _BLOCK_TAGS:
            parts.append("\n")

    walk(element)
    lines = (" ".join(line.split()) for line in "".join(parts).split("\n"))
    return "\n".join(line for line in lines if line)


def _required(root: Element, path: str) -> str:
    value = root.findtext(path)
    if value is None or not value.strip():
        raise LegiFormatError(f"élément obligatoire absent : {path}")
    return value.strip()


def _parse_date(raw: str, field: str) -> date:
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise LegiFormatError(f"date invalide pour {field} : {raw!r}") from exc


def _optional_date(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def _section_path(texte: Element) -> tuple[str, ...]:
    """Titres de structure (TM imbriqués) ; en cas de titres successifs au même
    niveau, le dernier publié est retenu et les autres restent dans le XML source."""
    path: list[str] = []
    node = texte.find("TM")
    while node is not None:
        titles = node.findall("TITRE_TM")
        if titles:
            path.append(" ".join((titles[-1].text or "").split()))
        node = node.find("TM")
    return tuple(p for p in path if p)


def parse_article(data: bytes, source_path: str) -> LegiArticle:
    """Analyse le contenu d'un fichier article LEGI."""
    try:
        root = SafeET.fromstring(data)
    except SafeET.ParseError as exc:
        raise LegiFormatError(f"XML invalide : {exc}") from exc
    if root.tag != "ARTICLE":
        raise LegiFormatError(f"racine inattendue : {root.tag}")

    official_id = _required(root, "META/META_COMMUN/ID")
    if not _ARTICLE_ID.match(official_id):
        raise LegiFormatError(f"identifiant d'article inattendu : {official_id}")
    meta = "META/META_SPEC/META_ARTICLE/"
    number = _required(root, meta + "NUM")
    status = _required(root, meta + "ETAT")
    raw_from = _required(root, meta + "DATE_DEBUT")
    raw_to = (root.findtext(meta + "DATE_FIN") or "").strip() or None

    valid_from = _parse_date(raw_from, "DATE_DEBUT")
    valid_to = None if raw_to is None else _parse_date(raw_to, "DATE_FIN")
    if valid_to is not None and valid_to >= OPEN_END_SENTINEL:
        valid_to = None

    texte = root.find("CONTEXTE/TEXTE")
    titre = root.find("CONTEXTE/TEXTE/TITRE_TXT")
    if texte is None or titre is None:
        raise LegiFormatError("bloc CONTEXTE/TEXTE absent")
    text_id = texte.get("cid") or titre.get("id_txt")
    if not text_id:
        raise LegiFormatError("identifiant du texte parent absent")

    content = _text_of(root.find("BLOC_TEXTUEL/CONTENU"))
    nota = _text_of(root.find("NOTA/CONTENU")) or None

    declared = tuple(
        DeclaredVersion(
            official_id=link.get("id", ""),
            status=link.get("etat", ""),
            raw_valid_from=link.get("debut", ""),
            raw_valid_to=link.get("fin"),
            number=link.get("num"),
        )
        for link in root.findall("VERSIONS/VERSION/LIEN_ART")
        if link.get("id")
    )
    links = tuple(
        LegiLink(
            link_type=link.get("typelien", ""),
            direction=link.get("sens"),
            target_official_id=link.get("id") or None,
            target_text_id=link.get("cidtexte") or None,
            target_label=" ".join((link.text or "").split()),
            target_date=_optional_date(link.get("datesignatexte")),
        )
        for link in root.findall("LIENS/LIEN")
    )

    return LegiArticle(
        official_id=official_id,
        number=number,
        status=status,
        raw_valid_from=raw_from,
        raw_valid_to=raw_to,
        period=LegalPeriod(valid_from=valid_from, valid_to=valid_to),
        text_official_id=text_id,
        text_nature=texte.get("nature") or "INCONNUE",
        text_title=" ".join((titre.text or "").split()),
        text_short_title=titre.get("c_titre_court") or None,
        section_path=_section_path(texte),
        content=content,
        content_sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
        nota=nota,
        declared_versions=declared,
        links=links,
        source_path=source_path,
        source_file_sha256=hashlib.sha256(data).hexdigest(),
    )
