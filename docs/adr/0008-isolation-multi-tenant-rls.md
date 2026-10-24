# ADR 0008 — Isolation multi-tenant par Row Level Security

**Statut** : acceptée le 2026-10-24 (voir `docs/decisions/registre-decisions.md`)

## Décision
* Base partagée, `organization_id` sur toutes les tables client.
* RLS **FORCE** sur ces tables, politique `organization_id = avx_current_tenant()`
  (paramètre de session `app.tenant_id` positionné par le serveur après
  authentification ; absent ⇒ aucune ligne).
* L'application se connecte avec `avx_app` : ni propriétaire, ni BYPASSRLS ;
  lecture seule sur le corpus ; insertion seule sur traces et journaux.
* Résolution du principal avant tenant : fonction `SECURITY DEFINER` dédiée,
  au périmètre limité.
* Défense en profondeur : contrôles d'autorisation applicatifs en plus de la RLS.

## Conséquences
+ Une requête oubliant le filtre tenant ne fuit pas (testé).
− Le pool de connexions doit réinitialiser `app.tenant_id` à chaque emprunt
  (`SET LOCAL` en transaction) — à implémenter en phase G (SEC-03).
− Option « base dédiée par tenant » à réévaluer pour les grands comptes.
