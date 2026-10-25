# ADR 0005 — BM25 dans PostgreSQL en V1, OpenSearch en phase D

**Statut** : acceptée le 2026-10-24 (voir `docs/decisions/registre-decisions.md`) ;
**bascule effectuée le 2026-10-25** (critères atteints, mesures ci-dessous)

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

## Mesures et bascule (2026-10-25)

Corpus complet (stock 2025-07-13 + 322 livraisons, 1 801 147 versions
courantes), 16 cas `seed_v0`, conteneur de développement (4 cœurs) :

| | BM25 PostgreSQL | OpenSearch 3.9.0 |
|---|---|---|
| Canal lexical, médiane / 95e centile | 17 000 ms / 75 700 ms | 14 ms / 20 ms |
| Réponse complète, médiane / 95e centile | 1 826 ms / 21 054 ms | 104 ms / 153 ms ¹ |
| Indexation complète | — | 4 min 40 s, index de 1,3 Go |

¹ après mise en cache des titres de textes (repliage de 147 187 titres à
chaque question : 1,5 s).

* Les critères de bascule (> 1 M de versions, 95e centile > 300 ms) sont
  atteints : OpenSearch devient le canal lexical dès qu'il est configuré
  (`AVX_OPENSEARCH_URL`) ; le BM25 PostgreSQL reste le repli (tests, poste
  sans OpenSearch).
* L'index n'est qu'une projection : les versions sont relues dans
  PostgreSQL, qui reste la source des citations et de leur vérification.
* Classement : BM25 sur le texte, renforcé par la proximité des termes dans
  les intitulés de section (calibrage provisoire, QUAL-01).
