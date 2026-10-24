"""Dates LEGI et valeurs sentinelles.

Valeurs observées dans les livraisons DILA (la documentation XML de 2018 ne
les définit pas ; voir ``docs/sources/verification-documentation-officielle.md``) :

* ``2999-01-01`` (et toute date ultérieure, ex. ``2999-12-31`` dans la DTD des
  sections) : absence de date — pas de fin pour une période, date inconnue
  pour une date de publication ;
* ``2222-02-22`` : date non encore fixée. Observée en fin de période
  d'articles ``ABROGE_DIFF`` dont la NOTA précise que les dispositions sont
  « maintenues en vigueur jusqu'à leur reprise par les mesures
  réglementaires », et en début de période d'éléments ``VIGUEUR_DIFF``.

Une sentinelle n'est jamais convertie en date réelle ; la valeur brute est
toujours conservée à côté de l'interprétation.
"""

from __future__ import annotations

from datetime import date

from avocat_expert.domain.temporal import LegalPeriod

NO_DATE_SENTINEL = date(2999, 1, 1)
UNDETERMINED_DATE_SENTINEL = date(2222, 2, 22)


class LegiDateError(ValueError):
    """Date absente ou illisible là où la source en exige une."""


def parse_raw_date(raw: str, field: str) -> date:
    try:
        return date.fromisoformat(raw)
    except ValueError as exc:
        raise LegiDateError(f"date invalide pour {field} : {raw!r}") from exc


def optional_date(raw: str | None) -> date | None:
    """Date informative (publication, signature…) : sentinelles et valeurs
    illisibles donnent ``None``."""
    if not raw:
        return None
    try:
        value = date.fromisoformat(raw)
    except ValueError:
        return None
    if value >= NO_DATE_SENTINEL or value == UNDETERMINED_DATE_SENTINEL:
        return None
    return value


def legal_period(raw_from: str, raw_to: str | None, field: str = "DATE_DEBUT/DATE_FIN") -> LegalPeriod:
    """Interprète un couple (début, fin) brut en période juridique."""
    start = parse_raw_date(raw_from, field)
    valid_from: date | None = start
    if start == UNDETERMINED_DATE_SENTINEL or start >= NO_DATE_SENTINEL:
        valid_from = None
    if raw_to is None:
        return LegalPeriod(valid_from=valid_from, valid_to=None)
    end = parse_raw_date(raw_to, field)
    if end == UNDETERMINED_DATE_SENTINEL:
        return LegalPeriod(valid_from=valid_from, valid_to=None, end_undetermined=True)
    if end >= NO_DATE_SENTINEL:
        return LegalPeriod(valid_from=valid_from, valid_to=None)
    return LegalPeriod(valid_from=valid_from, valid_to=end)
