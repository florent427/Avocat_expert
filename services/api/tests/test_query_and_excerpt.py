from __future__ import annotations

import pytest

from avocat_expert.search.excerpt import select_excerpt
from avocat_expert.search.query import parse_query, terms_of


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("article L. 5422-1 du code du travail", ("L5422-1",)),
        ("Que prévoit l'art. L5422-2 ?", ("L5422-2",)),
        ("R. 321-14 et D251-1", ("R321-14", "D251-1")),
        ("article 1240 du code civil", ("1240",)),
        ("allocation chômage durée", ()),
    ],
)
def test_article_numbers(raw: str, expected: tuple[str, ...]) -> None:
    assert parse_query(raw).article_numbers == expected


def test_official_ids() -> None:
    assert parse_query("voir LEGIARTI000048590547.").official_ids == ("LEGIARTI000048590547",)


def test_terms_fold_accents_and_drop_stopwords() -> None:
    assert terms_of("Les conditions d'éligibilité à l'allocation") == ("conditions", "eligibilite", "allocation")


def test_excerpt_is_literal() -> None:
    text = "Premier alinéa sans rapport avec la question posée.\nL'allocation est versée sous condition de ressources.\nAutre."
    excerpt = select_excerpt(text, terms_of("allocation versée"))
    assert excerpt == "L'allocation est versée sous condition de ressources."


def test_question_verbs_are_not_search_terms() -> None:
    assert parse_query("Que prévoit l'article L. 5422-2 ? Que dit le texte ?").terms == ("texte",)
