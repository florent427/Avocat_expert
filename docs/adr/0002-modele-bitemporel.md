# ADR 0002 — Modèle bitemporel et historique immuable

**Statut** : acceptée le 2026-10-24 (voir `docs/decisions/registre-decisions.md`)

## Contexte
Le droit applicable dépend de la date des faits ; la connaissance qu'a le
système d'une version évolue aussi (ex. la DATE_FIN d'une version LEGI passe
de `2999-01-01` à une date réelle lors d'une modification ultérieure ;
la DILA corrige par « annule et remplace »). Le cahier des charges exige de
distinguer validité juridique et date d'acquisition, et de ne jamais écraser
une version historique.

## Décision
* **Temps juridique** : `valid_from`, `valid_to` (NULL = pas de fin connue),
  intervalle **semi-ouvert** `[début, fin)` matérialisé dans `valid_period`
  (`daterange`, vide si `fin <= début` : versions « mort-nées » ou de durée nulle).
* **Temps de connaissance** : `sys_from`, `sys_to` (NULL = connaissance
  courante), `superseded_by`.
* Valeurs brutes de la source conservées (`raw_valid_from`, `raw_valid_to`,
  `source_status`).
* Insertion seule : un trigger refuse DELETE, la modification du contenu et
  toute modification d'une ligne close ; seules la fermeture de la période
  système et les marques de retrait sont permises.
* La sentinelle `2999-01-01` (et toute date ≥ 2999-01-01) est convertie en
  « pas de fin connue » par le connecteur.

## Justification de la convention semi-ouverte
Les chaînes de versions réelles enchaînent `DATE_FIN(n) = DATE_DEBUT(n+1)`
(ex. L5422-1 C. trav. : 2019-01-01 → 2022-12-23, puis 2022-12-23 → 2025-01-01).
**La documentation officielle obtenue ne précise pas le caractère inclusif ou
exclusif de DATE_FIN** : la convention est déduite des données et doit être
confirmée (DILA / juriste) — risque R-03.

## Conséquences
+ Requêtes « droit applicable au JJ/MM/AAAA » et « ce que le système savait au
  JJ/MM/AAAA » possibles ; corrections traçables.
− Volume accru (une ligne par changement de connaissance) ; index partiels.
