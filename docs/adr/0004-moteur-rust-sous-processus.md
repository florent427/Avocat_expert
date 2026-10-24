# ADR 0004 — Moteur déterministe Rust en sous-processus, contrat JSON versionné

**Statut** : acceptée le 2026-10-24 (registre des décisions) · 2026-10-24

## Contexte
Les vérifications de citation doivent être déterministes, auditables,
indépendantes des modèles et isolées de toute entrée réseau.

## Décision
Crate `lexverif` (bibliothèque + binaire). Interface : une requête JSON sur
stdin, une réponse sur stdout, `contract_version = "1"`, champs inconnus
refusés, entrée bornée à 8 Mio. Python l'invoque sans shell, avec délai.
Une indisponibilité du moteur est une erreur (HTTP 503), jamais un succès.

Alternatives écartées pour la V1 : PyO3 (couplage de build, débogage plus
difficile) ; service HTTP (surface réseau inutile). Réévaluation si la
latence du sous-processus devient significative (mesure en phase D).

## Conséquences
+ Frontière nette, testable par le contrat (tests Rust sur le binaire).
− Coût de lancement par appel (quelques ms) ; mode « lot » à prévoir.
