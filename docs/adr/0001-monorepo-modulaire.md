# ADR 0001 — Monorepo modulaire

**Statut** : acceptée le 2026-10-24 (registre des décisions) · 2026-10-24

## Contexte
Le projet combine une application web (TypeScript), un backend (Python), un
moteur déterministe (Rust), de l'infrastructure (Terraform), des contrats
partagés et un corpus d'évaluation. Les contrats doivent évoluer de manière
synchronisée entre ces composants.

## Décision
Un dépôt unique :

```
apps/web/            Next.js
services/api/        FastAPI : api, connectors, search, answer, verification, contracts, storage, observability, evaluation
services/api/migrations/  SQL versionné (NNNN_nom.sql), empreinte contrôlée
engine/              workspace Rust (crate lexverif)
packages/contracts/  schémas JSON exportés des contrats Pydantic (vérifiés en CI)
infra/terraform/     modules + environnements
eval/                corpus de cas
fixtures/            données publiques réelles pour les tests (provenance documentée)
docs/                architecture, ADR, conformité, backlog, rapports de phase
```

Le backend reste un **monolithe modulaire** : les modules communiquent par
contrats typés et peuvent être extraits en services (workers d'ingestion,
agents) sans changer les contrats.

## Conséquences
+ CI unique, changements atomiques sur les contrats.
− Outillage multi-langage (uv, cargo, npm, terraform) ; `Makefile` fourni.
