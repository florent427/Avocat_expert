# ADR 0011 — Authentification OIDC, mode développement fail-closed

**Statut** : acceptée le 2026-10-24 (voir `docs/decisions/registre-decisions.md`)

## Décision
* Cible : OIDC (code + PKCE côté web, jetons d'accès vérifiés côté API via
  JWKS, `iss`/`aud`/`exp` contrôlés), MFA obligatoire, rôles par organisation
  (`OWNER, ADMIN, LAWYER, ASSISTANT, READER, AUDITOR`). Fournisseur
  d'identité : **Keycloak auto-hébergé** (amendement DEC-02).
* V1 : mode `dev_token` (empreinte SHA-256, comparaison à temps constant)
  **refusé hors local/test** ; mode `oidc` déclaré mais **échoue fermé**
  (503) tant qu'il n'est pas implémenté.

## Amendement du 2026-10-24 (DEC-02)
Keycloak auto-hébergé, retenu pour sa portabilité (cohérence avec DEC-01).
À préciser à l'implémentation (SEC-01) : un realm unique avec une
organisation par cabinet, ou des groupes ; facteurs MFA (TOTP, WebAuthn) ;
durée des jetons ; exploitation (mises à jour de sécurité, sauvegardes,
haute disponibilité).
