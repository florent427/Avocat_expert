# Avocat Expert

Plateforme SaaS juridique française (en construction) : recherche, analyse
documentaire, préparation de dossiers et rapports juridiques **sourcés et
vérifiés**.

> **Statut : prototype interne — phase A.** Aucune mise en production. Les
> sorties ne constituent pas une consultation juridique. Les tests techniques
> ne remplacent pas la validation juridique professionnelle.

## Règles du projet
* Aucune information juridique inventée, aucune citation fictive acceptée,
  aucune conclusion incertaine présentée comme certaine.
* Chaque citation renvoie à une version précise d'une source officielle
  (identifiant, archive, empreinte) et passe par le moteur de vérification.
* Aucune intégration d'API sans spécification officielle vérifiée.
* Aucun secret ni donnée client dans le dépôt ; aucun déploiement sans
  validation explicite.

## Organisation

| Dossier | Contenu |
|---|---|
| `apps/web` | interface Next.js (prototype) |
| `services/api` | backend FastAPI : ingestion, recherche, réponse sourcée, vérification, contrats, traces |
| `engine` | moteur déterministe Rust `lexverif` |
| `packages/contracts` | schémas JSON des contrats |
| `infra/terraform` | infrastructure AWS eu-west-3 (validée, jamais appliquée) |
| `eval` | corpus d'évaluation |
| `fixtures` | données publiques réelles (DILA) pour les tests |
| `docs` | architecture, ADR, conformité, sources, modèle de données, backlog, rapports |

## Démarrage rapide

Prérequis : Python ≥ 3.12 + [uv](https://docs.astral.sh/uv/), Rust ≥ 1.82,
Node 22, PostgreSQL 16 avec `pgvector` et `unaccent`.

```bash
cd engine && cargo build && cd ..
cd services/api && uv sync
export AVX_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/avocat_expert
export AVX_LEXVERIF_BIN=$PWD/../../engine/target/debug/lexverif
uv run avx migrate
uv run avx ingest-legi ../../fixtures/legi/LEGI_20261023-215041
uv run avx answer "conditions d'attribution de l'allocation d'assurance" --as-of 2026-10-24

# tests (base PostgreSQL d'administration, une base temporaire est créée)
AVX_TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/postgres uv run pytest
```

Tout vérifier : `make check`.

## Documentation
* [Architecture V1](docs/architecture/architecture-v1.md)
* [ADR](docs/adr/README.md)
* [Dépendances réglementaires](docs/compliance/dependances-reglementaires.md)
* [Vérification des sources officielles](docs/sources/verification-documentation-officielle.md)
* [Modèle de données](docs/data-model/modele-donnees.md)
* [Contrats](docs/contracts/contrats-services-agents.md)
* [Backlog](docs/backlog/backlog-technique.md)
* [Rapport de phase A](docs/phases/phase-A-rapport.md)

## Attribution des données
Données LEGI : © DILA — Licence Ouverte v2.0 — https://echanges.dila.gouv.fr/OPENDATA/LEGI/
(fichier `LEGI_20261023-215041.tar.gz`, extraction du 2026-10-23).
