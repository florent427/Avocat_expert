"""Analyse des fichiers de textes et de structure LEGI.

Formats vérifiés sur les DTD officielles (``legi_texte_version.dtd``,
``legi_texte_struct.dtd``, ``legi_section_ta.dtd``, ``lien_*.dtd``,
archive ``DTD_LEGIFRANCE_20181017``) et sur la livraison réelle du 2026-10-23 :

* ``texte/version/LEGITEXT….xml`` (racine ``TEXTE_VERSION``) : une version
  d'un texte — titres, état, période, métadonnées de publication, visas,
  signataires, travaux préparatoires, nota, abrogation, rectificatif ;
* ``texte/struct/LEGITEXT….xml`` (racine ``TEXTELR``) : versions du texte
  (``VERSIONS``) et premier niveau de son plan (``STRUCT``) ;
* ``section_ta/LEGISCTA….xml`` (racine ``SECTION_TA``) : titre d'une section,
  sa suite ordonnée de sous-sections et d'articles (``STRUCTURE_TA``) et la
  chaîne de ses sections parentes (``CONTEXTE``).

Une section ne porte pas de dates : sa période et son état figurent sur le
lien qui la rattache à sa section (ou à son texte) parente.

``cid`` est l'identifiant commun à toutes les versions d'un texte (``LEGITEXT``
pour un code, ``JORFTEXT`` pour un texte non codifié) ; ``id`` identifie une
version.
"""

from __future__ import annotations

import hashlib
import re
from datetime import date
from typing import Literal
from xml.etree.ElementTree import Element

import defusedxml.ElementTree as SafeET
from pydantic import BaseModel, ConfigDict

from avocat_expert.connectors.legi.dates import LegiDateError, legal_period, optional_date
from avocat_expert.connectors.legi.parser import LegiFormatError, LegiLink, text_of
from avocat_expert.domain.temporal import LegalPeriod

_TEXT_ID = re.compile(r"^LEGITEXT\d{12}$")
_SECTION_ID = re.compile(r"^LEGISCTA\d{12}$")
_FILE_ID = re.compile(r"(LEGI(?:TEXT|SCTA)\d{12})\.xml$")

EntryKind = Literal["SECTION", "ARTICLE", "VERSION_TEXTE"]
NodeKind = Literal["TEXTE", "SECTION"]


class StructureEntry(BaseModel):
    """Lien ordonné d'un nœud vers une section, un article ou une version du texte."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    position: int
    kind: EntryKind
    target_official_id: str
    target_cid: str | None
    number: str | None
    label: str | None
    level: int | None
    status: str
    raw_valid_from: str
    raw_valid_to: str | None
    period: LegalPeriod
    origin: str | None


class ContextTitle(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    section_id: str
    title: str
    raw_valid_from: str
    raw_valid_to: str | None


class LegiStructureNode(BaseModel):
    """Racine du plan d'une version de texte, ou section."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: NodeKind
    official_id: str
    document_cid: str
    document_nature: str
    document_title: str | None
    title: str | None
    commentary: str | None
    context: tuple[tuple[ContextTitle, ...], ...]
    entries: tuple[StructureEntry, ...]
    source_path: str
    source_file_sha256: str


class LegiTextVersion(BaseModel):
    """Version d'un texte (``TEXTE_VERSION``)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    official_id: str
    document_cid: str
    nature: str
    title: str
    title_full: str | None
    status: str
    raw_valid_from: str
    raw_valid_to: str | None
    period: LegalPeriod
    number: str | None
    nor: str | None
    raw_publication_date: str | None
    publication_date: date | None
    raw_signature_date: str | None
    signature_date: date | None
    last_modified: date | None
    upcoming_versions: tuple[str, ...]
    publication_origin: str | None
    authority: str | None
    ministry: str | None
    visas: str | None
    signatories: str | None
    preparatory_work: str | None
    nota: str | None
    abrogation: str | None
    rectification: str | None
    links: tuple[LegiLink, ...]
    source_path: str
    source_file_sha256: str


def _root(data: bytes, expected: str) -> Element:
    try:
        root: Element = SafeET.fromstring(data)
    except SafeET.ParseError as exc:
        raise LegiFormatError(f"XML invalide : {exc}") from exc
    if root.tag != expected:
        raise LegiFormatError(f"racine inattendue : {root.tag} (attendu {expected})")
    return root


def _text(root: Element, path: str) -> str | None:
    value = root.findtext(path)
    if value is None:
        return None
    value = " ".join(value.split())
    return value or None


def _required(root: Element, path: str) -> str:
    value = _text(root, path)
    if value is None:
        raise LegiFormatError(f"élément obligatoire absent : {path}")
    return value


def _period(raw_from: str | None, raw_to: str | None, where: str) -> LegalPeriod:
    if not raw_from:
        raise LegiFormatError(f"date de début absente : {where}")
    try:
        return legal_period(raw_from, raw_to or None)
    except LegiDateError as exc:
        raise LegiFormatError(f"{where} : {exc}") from exc


def _entries(container: Element | None, *, start: int = 0) -> list[StructureEntry]:
    result: list[StructureEntry] = []
    if container is None:
        return result
    for element in container:
        kind: EntryKind
        if element.tag == "LIEN_SECTION_TA":
            kind = "SECTION"
        elif element.tag == "LIEN_ART":
            kind = "ARTICLE"
        else:
            raise LegiFormatError(f"élément de structure inattendu : {element.tag}")
        target = element.get("id")
        if not target:
            raise LegiFormatError(f"{element.tag} sans identifiant")
        level = element.get("niv")
        result.append(
            StructureEntry(
                position=start + len(result),
                kind=kind,
                target_official_id=target,
                target_cid=element.get("cid") or None,
                number=element.get("num") or None,
                label=" ".join((element.text or "").split()) or None,
                level=int(level) if level and level.isdigit() else None,
                status=element.get("etat", ""),
                raw_valid_from=element.get("debut", ""),
                raw_valid_to=element.get("fin") or None,
                period=_period(element.get("debut"), element.get("fin"), f"{element.tag} {target}"),
                origin=element.get("origine") or None,
            )
        )
    return result


def _file_id(source_path: str) -> str | None:
    match = _FILE_ID.search(source_path)
    return match.group(1) if match else None


def parse_text_structure(data: bytes, source_path: str) -> LegiStructureNode:
    """``texte/struct`` : versions du texte puis premier niveau du plan."""
    root = _root(data, "TEXTELR")
    official_id = _required(root, "META/META_COMMUN/ID")
    if not _TEXT_ID.match(official_id):
        raise LegiFormatError(f"identifiant de texte inattendu : {official_id}")
    versions: list[StructureEntry] = []
    for version in root.findall("VERSIONS/VERSION"):
        link = version.find("LIEN_TXT")
        if link is None or not link.get("id"):
            raise LegiFormatError("VERSION sans LIEN_TXT identifié")
        target = link.get("id", "")
        versions.append(
            StructureEntry(
                position=len(versions),
                kind="VERSION_TEXTE",
                target_official_id=target,
                target_cid=None,
                number=link.get("num") or None,
                label=None,
                level=None,
                status=version.get("etat", ""),
                raw_valid_from=link.get("debut", ""),
                raw_valid_to=link.get("fin") or None,
                period=_period(link.get("debut"), link.get("fin"), f"LIEN_TXT {target}"),
                origin=None,
            )
        )
    plan = _entries(root.find("STRUCT"), start=len(versions))
    return LegiStructureNode(
        kind="TEXTE",
        official_id=official_id,
        document_cid=_required(root, "META/META_SPEC/META_TEXTE_CHRONICLE/CID"),
        document_nature=_text(root, "META/META_COMMUN/NATURE") or "INCONNUE",
        document_title=None,
        title=None,
        commentary=None,
        context=(),
        entries=tuple(versions + plan),
        source_path=source_path,
        source_file_sha256=hashlib.sha256(data).hexdigest(),
    )


def _context(texte: Element) -> tuple[tuple[ContextTitle, ...], ...]:
    levels: list[tuple[ContextTitle, ...]] = []
    node = texte.find("TM")
    while node is not None:
        levels.append(
            tuple(
                ContextTitle(
                    section_id=title.get("id", ""),
                    title=" ".join((title.text or "").split()),
                    raw_valid_from=title.get("debut", ""),
                    raw_valid_to=title.get("fin") or None,
                )
                for title in node.findall("TITRE_TM")
            )
        )
        node = node.find("TM")
    return tuple(levels)


def parse_section(data: bytes, source_path: str) -> LegiStructureNode:
    """``section_ta`` : titre, sous-sections et articles ordonnés, contexte."""
    root = _root(data, "SECTION_TA")
    declared = _text(root, "ID")
    from_file = _file_id(source_path)
    official_id = declared or from_file
    if official_id is None or not _SECTION_ID.match(official_id):
        raise LegiFormatError(f"identifiant de section inattendu : {official_id}")
    if declared and from_file and declared != from_file:
        raise LegiFormatError(f"identifiant {declared} différent du nom de fichier {from_file}")
    texte = root.find("CONTEXTE/TEXTE")
    if texte is None:
        raise LegiFormatError("CONTEXTE/TEXTE absent")
    titles = texte.findall("TITRE_TXT")
    # cid absent (4 cas dans le stock) : même repli que pour les articles, sur
    # l'identifiant du texte porté par TITRE_TXT.
    cid = texte.get("cid") or (titles[-1].get("id_txt") if titles else None)
    if not cid:
        raise LegiFormatError("CONTEXTE/TEXTE sans cid ni id_txt")
    return LegiStructureNode(
        kind="SECTION",
        official_id=official_id,
        document_cid=cid,
        document_nature=texte.get("nature") or "INCONNUE",
        document_title=" ".join((titles[-1].text or "").split()) or None if titles else None,
        title=_required(root, "TITRE_TA"),
        commentary=_text(root, "COMMENTAIRE"),
        context=_context(texte),
        entries=tuple(_entries(root.find("STRUCTURE_TA"))),
        source_path=source_path,
        source_file_sha256=hashlib.sha256(data).hexdigest(),
    )


def parse_text_version(data: bytes, source_path: str) -> LegiTextVersion:
    """``texte/version`` : métadonnées et blocs textuels d'une version de texte."""
    root = _root(data, "TEXTE_VERSION")
    official_id = _required(root, "META/META_COMMUN/ID")
    if not _TEXT_ID.match(official_id):
        raise LegiFormatError(f"identifiant de texte inattendu : {official_id}")
    chronicle = "META/META_SPEC/META_TEXTE_CHRONICLE/"
    version = "META/META_SPEC/META_TEXTE_VERSION/"
    raw_from = _required(root, version + "DATE_DEBUT")
    raw_to = _text(root, version + "DATE_FIN")
    raw_publication = _text(root, chronicle + "DATE_PUBLI")
    raw_signature = _text(root, chronicle + "DATE_TEXTE")
    last_modified = _text(root, chronicle + "DERNIERE_MODIFICATION")
    links = tuple(
        LegiLink(
            link_type=link.get("typelien", ""),
            direction=link.get("sens"),
            target_official_id=link.get("id") or None,
            target_text_id=link.get("cidtexte") or None,
            target_label=" ".join((link.text or "").split()),
            target_date=optional_date(link.get("datesignatexte")),
        )
        for link in root.findall(version + "LIENS/LIEN")
    )

    def block(name: str) -> str | None:
        return text_of(root.find(f"{name}/CONTENU")) or None

    return LegiTextVersion(
        official_id=official_id,
        document_cid=_required(root, chronicle + "CID"),
        nature=_text(root, "META/META_COMMUN/NATURE") or "INCONNUE",
        title=_required(root, version + "TITRE"),
        title_full=_text(root, version + "TITREFULL"),
        status=_required(root, version + "ETAT"),
        raw_valid_from=raw_from,
        raw_valid_to=raw_to,
        period=_period(raw_from, raw_to, "META_TEXTE_VERSION"),
        number=_text(root, chronicle + "NUM"),
        nor=_text(root, chronicle + "NOR"),
        raw_publication_date=raw_publication,
        publication_date=optional_date(raw_publication),
        raw_signature_date=raw_signature,
        signature_date=optional_date(raw_signature),
        last_modified=optional_date(last_modified),
        upcoming_versions=tuple(
            " ".join((v.text or "").split()) for v in root.findall(chronicle + "VERSIONS_A_VENIR/VERSION_A_VENIR")
        ),
        publication_origin=_text(root, chronicle + "ORIGINE_PUBLI"),
        authority=_text(root, version + "AUTORITE"),
        ministry=_text(root, version + "MINISTERE"),
        visas=block("VISAS"),
        signatories=block("SIGNATAIRES"),
        preparatory_work=block("TP"),
        nota=block("NOTA"),
        abrogation=block("ABRO"),
        rectification=block("RECT"),
        links=links,
        source_path=source_path,
        source_file_sha256=hashlib.sha256(data).hexdigest(),
    )
