# ADR 0005 — BM25 dans PostgreSQL en V1, OpenSearch en phase D

**Statut** : acceptée le 2026-10-24 (voir `docs/decisions/registre-decisions.md`)

## Contexte
Le cahier des charges prévoit OpenSearch + pgvector. La tranche verticale
doit fonctionner et être testée sans service supplémentaire. Un essai avec
`ts_rank_cd` a montré un biais en faveur des textes longs (L125-2 C. assur.
classé devant L5422-2 C. trav. sur une question d'indemnisation chômage).

## Décision
* V1 : BM25 (k1=1,2 ; b=0,75) calculé en SQL à partir des positions des
  lexèmes du `tsvector` (configuration `avx_fr` : français + `unaccent`),
  statistiques de corpus en vues matérialisées rafraîchies après ingestion.
* Le canal lexical est derrière le port `LexicalSearcher` : l'adaptateur
  OpenSearch (analyseur français, BM25 natif) sera ajouté en phase D et
  comparé sur le même corpus d'évaluation avant bascule.
* Critères de bascule : corpus > ~1 M versions, latence p95 > 300 ms,
  besoin d'analyseurs (synonymes juridiques) — à mesurer.

## Conséquences
+ Aucun service supplémentaire en V1 ; résultats mesurés.
− Fréquences de termes plafonnées (256 positions par lexème dans PostgreSQL) ;
  coût de calcul croissant avec le nombre de candidats.
