# Rapport de validation — Phase D (recherche à l'échelle)

Date : 2026-10-25 · Branche : `ccr-f9391166-37sdlt`. Aucune ressource cloud,
aucun coût, aucun service tiers. Mesures sur un conteneur de développement
(4 cœurs, 15 Go de mémoire, sans processeur graphique), corpus LEGI de la
phase C (date de connaissance 2026-06-01, 1 801 147 versions courantes).

## 1. Objectifs et état

| Objectif | État | Livrables |
|---|---|---|
| SRCH-01 Canal lexical OpenSearch | ✅ | `search/opensearch.py`, `search/indexer.py`, migration 0012, ADR 0005 |
| SRCH-02 Canal sémantique auto-hébergé (DEC-07) | ✅ | `embedding/`, migration 0013, ADR 0017, `docs/ops/recherche-semantique.md` |
| Jeu d'évaluation à l'échelle | ✅ 28 questions (`AVIS_IA_DELEGUE`) | `eval/cases/echelle_v0.jsonl` |
| SRCH-03 Reranking | ⏳ après QUAL-01 | |
| INFRA-10 OpenSearch géré en recette | ⏳ recette locale d'abord (DEC-06) | |

Tests : Rust 27, Python 138 (PostgreSQL, OpenSearch, modèle d'embeddings et
moteur réels ; aucun ignoré), web ; CI verte, y compris le test de fumée de
la pile `docker compose` avec le canal sémantique.

## 2. Canal lexical (SRCH-01)

| Corpus complet | BM25 PostgreSQL (phase C) | OpenSearch 3.9.0 |
|---|---|---|
| Canal lexical, médiane / 95e centile | 17 000 ms / 75 700 ms | 14 ms / 20 ms |
| Réponse complète, médiane / 95e centile | 1 826 ms / 21 054 ms | 104 ms / 153 ms |
| Indexation complète | — | 4 min 40 s, 1,3 Go |

Restriction au texte nommé dans la question appliquée par le moteur ;
proximité des termes dans les intitulés de section (L5422-1 : du rang > 200
au rang 6 pour « conditions d'attribution de l'allocation d'assurance »).

## 3. Canal sémantique (SRCH-02)

### Sélection du modèle

Voir ADR 0017 : quatre variantes auto-hébergeables comparées sur les 28
questions dans un ensemble commun de 3 836 articles.

| Modèle | MRR@10 | Rappel@1 | Rappel@10 | Débit relatif |
|---|---|---|---|---|
| multilingual-e5-small | 0,363 | 0,250 | 0,607 | 2,4 |
| multilingual-e5-base int8 | 0,411 | 0,286 | 0,679 | 3,3 |
| **multilingual-e5-base (retenu)** | 0,519 | 0,429 | 0,821 | 1 |
| bge-m3 | 0,591 | 0,429 | 0,857 | 0,4 |

### Fixtures (16 cas)

| | Lexical OpenSearch | Hybride (e5-base, écart 0,015) |
|---|---|---|
| Rappel moyen | 0,9231 | **1,0** |
| Précision moyenne | 0,8077 | 0,8205 |
| Intégrité des contrôles déterministes | 1,0 | 1,0 |
| Échecs | SEED-014 | **aucun** |

Écart de similarité : 0,005 à 0,015 font aboutir SEED-014 sans perte de
précision ; 0,03 le perd à nouveau, 0,05 fait tomber la précision à 0,64
(dispositions voisines du même chapitre ajoutées).

### Corpus complet

Vecteurs calculés pour les 46 181 articles en vigueur au 2026-06-01 de sept
codes (travail, civil, pénal, consommation, commerce, santé publique,
sécurité sociale), corpus LEGI complet pour le canal lexical ; index
OpenSearch reconstruit (1 801 147 documents, 6 min 13 s, 1,5 Go).

| Configuration (3 citations, 28 questions) | Trouvés | Rappel@3 | MRR |
|---|---|---|---|
| Lexical, corpus complet | 3 | 0,107 | 0,107 |
| Lexical, sept codes | 7 | 0,250 | 0,208 |
| **Hybride, sept codes** | **14** | **0,500** | **0,375** |

* Le canal sémantique double les questions abouties à périmètre égal ;
  14 questions restent sans l'article attendu (reclassement SRCH-03,
  corpus annoté QUAL-01).
* Intégrité des contrôles déterministes : 1,0 dans toutes les configurations
  (84 citations vérifiées par lexverif).
* Temps : vectorisation d'une question 17 ms en médiane (27 ms au 95e
  centile), canal sémantique complet 31 ms (40 ms) ; réponse complète
  0,15 s par question en moyenne, vérification comprise.
* Vectorisation : 11 articles/s sur 4 cœurs ; vecteur de 3,1 Ko par texte
  distinct.

## 4. Sécurité et conformité

* Aucun texte ni aucune question envoyés à un tiers ; seule sortie réseau :
  le téléchargement initial des fichiers du modèle, épinglés par empreinte
  (fichier altéré refusé : vérifié).
* Fichiers de données seulement (ONNX, JSON) ; `HF_HUB_OFFLINE=1` dans
  l'image ; dépendance transitive `filelock` relevée en 4.2.4
  (GHSA-v4x8-3wr5-3wq8).
* Vecteurs en insertion seule, rangés par modèle ; le canal ne peut pas
  interroger un index construit par un autre modèle.

## 5. Limites

* 28 questions rédigées et annotées par Claude sur délégation : ordre de
  grandeur, pas une mesure de qualité juridique (QUAL-01).
* Articles de plus de 512 jetons : fin non vectorisée.
* Vectorisation du corpus complet : environ 45 heures sur 4 cœurs ; instance
  de calcul ponctuelle à prévoir pour la recette (décision du porteur).
* Mesures sur sept codes : un corpus entièrement vectorisé ajouterait des
  voisins d'autres textes (à remesurer en recette).
* Environnement de développement suspendu pendant l'inactivité de la session
  (redémarrages constatés) : calculs longs repris grâce à l'idempotence de
  `avx calculer-embeddings`.

## 6. Actions du porteur du projet

1. Valider le choix du modèle (ADR 0017) ou demander la réévaluation de
   bge-m3 sur le corpus annoté.
2. Recette : autoriser une instance de calcul ponctuelle pour vectoriser le
   corpus complet (coût à chiffrer avant tout engagement).
3. QUAL-01 : faire relire par un juriste les 28 questions d'échelle et les
   16 cas d'amorçage.
