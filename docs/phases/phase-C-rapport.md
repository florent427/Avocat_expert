# Rapport de validation — Phase C (corpus LEGI à l'échelle)

Date : 2026-10-24 · Branche : `ccr-f9391166-37sdlt`. Aucune ressource cloud,
aucun coût. Données : stock et livraisons publics de la DILA (Licence
Ouverte 2.0), téléchargés depuis https://echanges.dila.gouv.fr/OPENDATA/LEGI/.
Mesures sur un conteneur de développement (4 cœurs, 15 Go de mémoire,
PostgreSQL 16 + pgvector 0.8.7 en conteneur), non représentatives d'une
instance RDS dimensionnée.

## 1. Objectifs et état

| Objectif | État | Livrables |
|---|---|---|
| ING-01 Textes, plan et sections | ✅ | `connectors/legi/structure.py`, migration 0008, `storage/structure.py` |
| ING-02 Stock en flux, lots, reprise, ordre des livraisons | ✅ | `connectors/legi/{archive,ingest,remote}.py`, `avx sync-legi`, `docs/ops/ingestion-legi.md` |
| ING-10 Supervision de fraîcheur | ✅ | `avx fraicheur-legi` |
| R-07 Mesure à l'échelle | ✅ mesurée — **seuil dépassé** pour la recherche (§ 4) | |
| Jurisprudence (ING-05/06) | ⏳ compte PISTE en attente (DEC-05) | |

## 2. Défauts trouvés sur données réelles et corrigés

Tous découverts en confrontant le code au stock complet et aux livraisons
réelles ; aucun n'apparaissait sur les 40 fichiers de la phase A.

| # | Constat | Conséquence avant correction | Correction |
|---|---|---|---|
| 1 | `2222-02-22` (et `2222-01-01`) : date d'abrogation ou d'entrée en vigueur **non fixée** | art. 289 CGI déclaré « en vigueur » avec certitude en 2030, réponse « jusqu'au 2222-02-22 » | date non fixée, état indéterminé au-delà de la date de connaissance (ADR 0016, moteur contrat v2) |
| 2 | 229 644 articles sans état ni date (`2999-01-01` en début) | rejet de 13 % du stock | dates inconnues, toujours indéterminées (0009) |
| 3 | `ETAT` vide avec dates | citation présentée comme conforme | au mieux INCERTAINE |
| 4 | 25 121 articles non numérotés | rejet ; fusion de deux articles distincts | identité par plus petit identifiant de version |
| 5 | 4 sections sans `cid`, 280 936 index ELI | rejet ; fichiers ignorés non comptés | repli sur `id_txt` ; ELI comptés à part |
| 6 | 12 143 articles et 1 945 sections **présents dans deux branches** du stock, 5 546 copies divergentes (ex. `ABROGE_DIFF` / `ABROGE`) | version retenue selon l'ordre de lecture de l'archive (copie périmée dans des milliers de cas) | la copie la plus récente (horodatage du fichier) fait foi (0010) |
| 7 | `tarfile` conserve chaque en-tête lu, même en flux | plus de 3 Go de mémoire sur le stock | purge à chaque membre : 77 à 530 Mo |
| 8 | une requête synchrone par lecture d'état | 200 fichiers/s, 3 h pour le stock | lots préchargés, pipeline : 700 fichiers/s (2 500/s inchangés) |
| 9 | statistiques BM25 recalculées après chaque livraison (32 s) | plus de 4 h pour 474 livraisons | une fois par synchronisation |
| 10 | index unique de `legal_reference` (6 colonnes texte) | 4,7 Go, saturation du disque au rejeu | dédoublonnage par le connecteur (0011) |
| 11 | copie périmée d'un plan de texte écrite (issue ignorée) | bloquée par l'index unique, lot annulé | corrigé, test qui échoue sans la correction |

## 3. Résultats des tests

* Rust : 27 réussis (dont dates non fixées, dates inconnues, état vide).
* Python : 119 réussis, aucun ignoré (PostgreSQL réel et moteur Rust).
* Web : lint, types générés, construction ; CI verte sur la branche.
* Évaluation sur fixtures (16 cas, AVIS_IA_DELEGUE) : précision 0,7821,
  intégrité des contrôles déterministes 0,95 — la 20e citation (art. 289 CGI)
  est à juste titre INDETERMINEE (§ 2, n° 1).

## 4. Mesures à l'échelle (R-07)

### Ingestion

| | Stock 2025-07-13 | 322 livraisons (2025-07-13 → 2026-06-01) |
|---|---|---|
| Fichiers XML | 2 276 109 (+ 280 936 index ELI) | 981 532 |
| Rejets | **0** | **0** |
| Insertions / remplacements / inchangés | 2 193 797 / 15 747 / 66 565 | 96 664 / 477 245 / 407 623 |
| Durée | 45 min (lecture initiale, 700 fichiers/s) ; relecture 15 min | 61 min (11 s par livraison en moyenne ; maximum 27 241 fichiers) |
| Mémoire maximale | 530 Mo | 400 Mo |
| Reprises après incident | 3 réelles (redémarrage de PostgreSQL, arrêt du processus, défaut du connecteur) | 1 (disque saturé) |
| Retraits | — | 42 041 entrées, 9 700 appliquées ; non appliquées : 12 216 changements de branche (version courante sous un autre chemin), 6 729 déjà retirées, 11 328 identifiants absents du corpus |

### Volumétrie (corpus au 2026-06-01)

* 1 807 645 versions d'articles courantes (688 996 en vigueur au 2026-10-24),
  459 532 versions historiques ; 147 177 textes, 151 216 versions de textes,
  398 170 nœuds de plan, 2 990 521 entrées de plan ; 1 873 fins non fixées,
  248 110 articles à dates inconnues.
* Base : **17,3 Go**, dont `provision_version` 7,8 Go et `legal_reference`
  6,4 Go (chaque nouvelle version d'article reprend son bloc de liens).
* Croissance mesurée : ~6 Go pour 10,5 mois de livraisons (après correction
  n° 10). Les 152 livraisons restantes (juin → octobre 2026) n'ont pas été
  appliquées faute d'espace disque dans le conteneur ; état cohérent
  (dernière livraison réussie, date de connaissance 2026-06-01).

### Recherche et réponse (16 cas, corpus au 2026-06-01)

| | Médiane | 95e centile | Maximum |
|---|---|---|---|
| BM25 en SQL (canal lexical seul) | **17,0 s** | **75,7 s** | 76,1 s |
| Réponse complète (recherche + vérification) | 1,8 s | 21,1 s | 21,9 s |

* **R-07 confirmé** : le BM25 calculé dans PostgreSQL est inutilisable à
  l'échelle du corpus (des millions de candidats pour une requête courante).
  Un moteur dédié (OpenSearch, ADR 0003, phase D) est requis avant toute
  recette ouverte à des utilisateurs.
* Pertinence : les cas citant un identifiant ou un numéro d'article
  aboutissent (6 sur 6) ; les **quatre questions en langage naturel
  échouent** (articles d'autres textes en tête). Avec 40 articles, le
  classement lexical suffisait ; avec 1,8 million, non. Nécessaires :
  restriction au domaine ou au texte, canal sémantique, évaluation sur un
  corpus annoté par des juristes (VAL-01).
* Bitemporalité observée sur données réelles : au 2026-06-01, la nouvelle
  version de l'art. L161-1 CIBS devait entrer en vigueur le 2026-09-01 ;
  une livraison postérieure l'a reportée au 2027-01-01 (fixtures du
  2026-10-23). Le cas SEED-010, construit sur la connaissance la plus
  récente, échoue donc sur ce corpus — la réponse signale que la date
  demandée est postérieure à la dernière livraison intégrée.

## 5. Limites et risques

* Mesures sur un conteneur de développement ; à refaire sur l'instance de
  recette (classe RDS, stockage) avant dimensionnement définitif.
* Sémantique des sentinelles et du double classement en branches déduite des
  données et des NOTA, non confirmée par la DILA (ING-03).
* Retraits sur identifiants absents du corpus (11 328) : à analyser (ING-03).
* Croissance de `legal_reference` : stocker les blocs de liens par empreinte
  (une copie par contenu distinct) diviserait son volume (ING-09).
* Jurisprudence non ingérée (PISTE).

## 6. Actions du porteur du projet

1. Compte PISTE (bac à sable) et identifiants en secrets d'environnement :
   condition des connecteurs Judilibre et justice administrative.
2. Arbitrer la priorité de la phase D (OpenSearch et canal sémantique) : la
   recherche en SQL n'est pas exploitable sur le corpus réel.
3. Dimensionnement de recette : prévoir au moins 50 Go de stockage pour la
   base (17 Go mesurés à 10,5 mois, croissance d'environ 7 Go par an,
   index de recherche en sus).
