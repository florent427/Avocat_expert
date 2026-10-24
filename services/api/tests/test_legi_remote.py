"""Inventaire et plan d'application des livraisons LEGI (index réel du 2026-10-24)."""

from __future__ import annotations

from datetime import datetime

import pytest

from avocat_expert.connectors.legi.remote import RemoteError, _checked, freshness, parse_index, plan

from .conftest import REPO_ROOT

INDEX = REPO_ROOT / "fixtures" / "legi" / "index" / "OPENDATA_LEGI_extrait_20261024.html"


def test_index_lists_stock_and_deltas_in_order() -> None:
    archives = parse_index(INDEX.read_text("utf-8"))
    assert [a.name for a in archives] == [
        "LEGI_20250712-211706.tar.gz",
        "Freemium_legi_global_20250713-140000.tar.gz",
        "LEGI_20250713-205013.tar.gz",
        "LEGI_20250715-205701.tar.gz",
        "LEGI_20261023-215041.tar.gz",
    ]
    assert [a.is_stock for a in archives].count(True) == 1


def test_first_integration_starts_with_latest_stock() -> None:
    archives = parse_index(INDEX.read_text("utf-8"))
    names = [a.name for a in plan(archives, None)]
    # La livraison du 2025-07-12, antérieure au stock, n'est pas appliquée.
    assert names == [
        "Freemium_legi_global_20250713-140000.tar.gz",
        "LEGI_20250713-205013.tar.gz",
        "LEGI_20250715-205701.tar.gz",
        "LEGI_20261023-215041.tar.gz",
    ]


def test_following_integrations_apply_only_later_deltas() -> None:
    archives = parse_index(INDEX.read_text("utf-8"))
    names = [a.name for a in plan(archives, datetime(2025, 7, 15, 20, 57, 1))]
    assert names == ["LEGI_20261023-215041.tar.gz"]
    assert plan(archives, datetime(2026, 10, 23, 21, 50, 41)) == []


def test_no_stock_means_no_first_integration() -> None:
    archives = [a for a in parse_index(INDEX.read_text("utf-8")) if not a.is_stock]
    with pytest.raises(RemoteError, match="aucun stock"):
        plan(archives, None)


@pytest.mark.parametrize(
    "url",
    [
        "http://echanges.dila.gouv.fr/OPENDATA/LEGI/",
        "https://echanges.dila.gouv.fr.example.org/OPENDATA/LEGI/",
        "https://exemple.invalid/LEGI_20261023-215041.tar.gz",
    ],
)
def test_network_egress_is_restricted_to_the_official_host(url: str) -> None:
    with pytest.raises(RemoteError, match="hors du périmètre"):
        _checked(url)


def test_freshness_reports_pending_deliveries_and_lag() -> None:
    archives = parse_index(INDEX.read_text("utf-8"))
    late = freshness(archives, datetime(2025, 7, 15, 20, 57, 1))
    assert not late.up_to_date and late.pending == ("LEGI_20261023-215041.tar.gz",)
    assert late.lag_days is not None and late.lag_days > 465
    current = freshness(archives, datetime(2026, 10, 23, 21, 50, 41))
    assert current.up_to_date and current.lag_days == 0
    assert not freshness(archives, None).up_to_date  # corpus vide
