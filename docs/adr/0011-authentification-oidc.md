# ADR 0011 — Authentification OIDC, mode développement fail-closed

**Statut** : proposée — partiellement implémentée · 2026-10-24

## Décision
* Cible : OIDC (code + PKCE côté web, jetons d'accès vérifiés côté API via
  JWKS, `iss`/`aud`/`exp` contrôlés), MFA obligatoire, rôles par organisation
  (`OWNER, ADMIN, LAWYER, ASSISTANT, READER, AUDITOR`). Fournisseur
  d'identité à choisir (❓ : Cognito, Keycloak auto-hébergé, autre).
* V1 : mode `dev_token` (empreinte SHA-256, comparaison à temps constant)
  **refusé hors local/test** ; mode `oidc` déclaré mais **échoue fermé**
  (503) tant qu'il n'est pas implémenté.
