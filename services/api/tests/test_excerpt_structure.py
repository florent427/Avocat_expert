"""Choix des extraits sur les textes réels : jamais de phrase introductive
privée de son énumération, jamais d'item isolé de sa phrase introductive."""

from __future__ import annotations

import json
import subprocess
from datetime import date
from pathlib import Path

import pytest

from avocat_expert.connectors.legi.archive import iter_article_files
from avocat_expert.connectors.legi.parser import LegiArticle, parse_article
from avocat_expert.search.excerpt import ELISION, MIN_SEGMENT_CHARS, is_item, parse_structure, select_excerpt
from avocat_expert.search.query import terms_of

QUERIES = [
    "",
    "quand cesse le versement du revenu de remplacement",
    "inscription sur la liste des demandeurs d'emploi",
    "conditions d'attribution de l'allocation d'assurance",
    "électricité hydrogène source exclusive d'énergie",
    "masse en ordre de marche",
    "catastrophes naturelles délai d'indemnisation",
    "déclaration des impositions",
    "refus de deux propositions de contrat à durée indéterminée",
]


@pytest.fixture(scope="module")
def articles(legi_fixtures: Path) -> list[LegiArticle]:
    return [parse_article(e.data, e.path) for e in iter_article_files(legi_fixtures)]


def _by_id(articles: list[LegiArticle], official_id: str) -> LegiArticle:
    return next(a for a in articles if a.official_id == official_id)


def _segments(excerpt: str) -> list[str]:
    return [s.strip("\n") for s in excerpt.split(ELISION) if s.strip()]


def test_enumeration_is_cited_with_its_introduction(articles: list[LegiArticle]) -> None:
    article = _by_id(articles, "LEGIARTI000051289909")  # L5421-4 C. trav.
    excerpt = select_excerpt(article.content, terms_of("quand cesse le versement du revenu de remplacement"))
    assert excerpt.startswith("Le revenu de remplacement cesse d'être versé :")
    assert all(f"\n{n}° " in excerpt for n in (1, 2, 3))
    assert ELISION not in excerpt  # l'article tient dans le budget : énumération complète


def test_isolated_item_comes_with_its_introduction(articles: list[LegiArticle]) -> None:
    article = _by_id(articles, "LEGIARTI000048173002")  # D251-1 C. énergie, 4 445 caractères
    excerpt = select_excerpt(article.content, terms_of("électricité hydrogène source exclusive d'énergie"))
    assert excerpt.startswith("I.-Une aide, dite bonus écologique")
    assert (
        "5° Utilise l'électricité, l'hydrogène ou une combinaison des deux comme source exclusive d'énergie ;"
        in excerpt
    )
    assert ELISION in excerpt  # trop long : phrase introductive + items pertinents


def test_sub_items_keep_both_ancestors(articles: list[LegiArticle]) -> None:
    article = _by_id(articles, "LEGIARTI000048173002")
    excerpt = select_excerpt(article.content, terms_of("masse en ordre de marche"))
    lines = excerpt.split("\n")
    assert lines[0].startswith("I.-Une aide")
    assert any(line.startswith("6° Vérifie les conditions additionnelles suivantes :") for line in lines)
    assert any(line.startswith("b) Sa masse en ordre de marche") for line in lines)


def test_structure_parsing_of_nested_enumeration(articles: list[LegiArticle]) -> None:
    root = parse_structure(_by_id(articles, "LEGIARTI000048173002").content)
    section = root.children[0]
    assert section.line.startswith("I.-")
    sixth = next(c for c in section.children if c.line.startswith("6°"))
    assert [c.line[:2] for c in sixth.children] == ["a)", "b)", "c)"]
    assert root.children[1].line.startswith("II.-")


@pytest.mark.parametrize("query", QUERIES)
def test_invariants_on_all_real_articles(articles: list[LegiArticle], query: str) -> None:
    for article in articles:
        excerpt = select_excerpt(article.content, terms_of(query))
        assert excerpt, article.official_id
        lines = [line for line in excerpt.split("\n") if line != ELISION]
        source_lines = article.content.split("\n")
        assert all(line in source_lines for line in lines), article.official_id
        positions = [source_lines.index(line) for line in lines]
        assert positions == sorted(positions), f"ordre non respecté : {article.official_id}"
        first_is_item = is_item(lines[0]) and not is_item(source_lines[0])
        assert not first_is_item, f"item isolé en tête : {article.official_id}"
        assert not lines[-1].endswith(":") or lines[-1] == source_lines[-1], (
            f"phrase introductive orpheline : {article.official_id}"
        )
        for segment in _segments(excerpt):
            assert sum(not c.isspace() for c in segment) >= MIN_SEGMENT_CHARS or len(_segments(excerpt)) == 1


@pytest.mark.engine
def test_every_excerpt_passes_the_rust_verifier(articles: list[LegiArticle], lexverif_bin: str) -> None:
    for query in QUERIES:
        for article in articles:
            excerpt = select_excerpt(article.content, terms_of(query))
            period = {
                "official_id": article.official_id,
                "valid_from": article.period.valid_from.isoformat() if article.period.valid_from else None,
                "valid_to": article.period.valid_to.isoformat() if article.period.valid_to else None,
                "end_undetermined": article.period.end_undetermined,
                "status_raw": article.status,
            }
            request = {
                "contract_version": "2",
                "command": "verify_citation",
                "payload": {
                    "citation": {
                        "official_id": article.official_id,
                        "quote": excerpt,
                        "as_of": date(2026, 10, 24).isoformat(),
                        "territory": None,
                    },
                    "candidate": {
                        "official_id": article.official_id,
                        "text": article.content,
                        "period": period,
                        "territorial_scope": None,
                    },
                    "sibling_versions": [period],
                },
            }
            out = subprocess.run([lexverif_bin], input=json.dumps(request).encode(), capture_output=True, check=True)
            checks = {c["check"]: c["outcome"] for c in json.loads(out.stdout)["result"]["checks"]}
            assert checks["PASSAGE_PRESENT"] == "OK", (article.official_id, query, excerpt[:200])
