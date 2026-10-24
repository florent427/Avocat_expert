"""Dates LEGI et valeurs sentinelles.

Valeurs observées dans les livraisons DILA (la documentation XML de 2018 ne
les définit pas ; voir ``docs/sources/verification-documentation-officielle.md``) :

* ``2999-01-01`` (et toute date ultérieure, ex. ``2999-12-31`` dans la DTD des
  sections) : absence de date — pas de fin pour une période, date inconnue
  pour une date de publication ; en **début** de période (stock du
  2025-07-13 : articles de versions JORF d'origine, ``ETAT`` vide, fin
  également à 2999-01-01), dates d'application non renseignées ;
* ``2222-02-22`` : date non encore fixée. Observée en fin de période
  d'articles ``ABROGE_DIFF`` dont la NOTA précise que les dispositions sont
  « maintenues en vigueur jusqu'à leur reprise par les mesures
  réglementaires », et en début de période d'éléments ``VIGUEUR_DIFF`` ;
  variante ``2222-01-01`` (stock du 2025-07-13, texte ``ABROGE_DIFF``) : toute
  date de l'année 2222 est traitée comme non fixée.

Une sentinelle n'est jamais convertie en date réelle ; la valeur brute est
toujours conservée à côté de l'interprétation.
"""

from __future__ import annotations

from datetime import date

from avocat_expert.domain.temporal import LegalPeriod

NO_DATE_SENTINEL = date(2999, 1, 1)
UNDETERMINED_DATE_SENTINEL = date(2222, 2, 22)
UNDETERMINED_YEAR = 2222


def is_undetermined(value: date) -> bool:
    return value.year == UNDETERMINED_YEAR


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
    if value >= NO_DATE_SENTINEL or is_undetermined(value):
        return None
    return value


def legal_period(raw_from: str, raw_to: str | None, field: str = "DATE_DEBUT/DATE_FIN") -> LegalPeriod:
    """Interprète un couple (début, fin) brut en période juridique."""
    start = parse_raw_date(raw_from, field)
    if start >= NO_DATE_SENTINEL:
        # Aucune date d'application connue : la fin éventuelle reste exploitable.
        end = None if raw_to is None else parse_raw_date(raw_to, field)
        real_end = end if end is not None and end < NO_DATE_SENTINEL and not is_undetermined(end) else None
        return LegalPeriod(valid_from=None, valid_to=real_end, dates_unknown=True)
    valid_from: date | None = None if is_undetermined(start) else start
    if raw_to is None:
        return LegalPeriod(valid_from=valid_from, valid_to=None)
    end = parse_raw_date(raw_to, field)
    if is_undetermined(end):
        return LegalPeriod(valid_from=valid_from, valid_to=None, end_undetermined=True)
    if end >= NO_DATE_SENTINEL:
        return LegalPeriod(valid_from=valid_from, valid_to=None)
    return LegalPeriod(valid_from=valid_from, valid_to=end)
