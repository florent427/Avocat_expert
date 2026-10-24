# ADR 0012 — Traçabilité sans fuite de données confidentielles

**Statut** : proposée — implémentée · 2026-10-24

## Décision
* Traces d'exécution, étapes et coûts : empreintes SHA-256, longueurs,
  identifiants, statuts, versions de composants. Jamais le texte d'une
  question, d'un document ou d'une réponse générée.
* Journal d'accès en insertion seule (trigger + privilèges).
* Les journaux applicatifs suivent la même règle (revue en phase I, tests
  automatiques de non-fuite).
* OpenTelemetry (phase B/I) : attributs filtrés par liste blanche.

Limite : une empreinte d'un texte court et prévisible peut être retrouvée par
force brute ; pour les données client, utiliser un HMAC avec clé par tenant
(backlog SEC-06).
