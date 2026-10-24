# Rapport de validation — Phase B (socle : conteneurs, CI/CD, infrastructure)

Date : 2026-10-24 · Branche : `ccr-f9391166-37sdlt`. Aucun déploiement,
aucune ressource cloud créée, aucun coût engagé.

## 1. Objectifs et état

| Objectif | État | Livrables |
|---|---|---|
| Images de conteneurs durcies | ✅ | `services/api/Dockerfile`, `apps/web/Dockerfile`, `.dockerignore` |
| Analyse des images et SBOM | ✅ | job CI `images` (Trivy bloquant, CycloneDX) |
| Pile locale complète et testée | ✅ | `docker-compose.yml`, `scripts/smoke-compose.sh` |
| Fournisseur d'identité (DEC-02) | ✅ configuration | `infra/keycloak/realm-avocat-expert.json` (vérification des jetons dans l'API : SEC-01, phase G) |
| Infrastructure AWS (Terraform) | ✅ validée, non appliquée | `infra/terraform/modules/*`, `envs/staging` |
| Observabilité | ✅ traces | `observability/telemetry.py`, ADR 0015 |
| Sauvegarde / restauration testées | ✅ | `tests/test_backup_restore.py`, `docs/ops/sauvegarde-restauration.md` |
| Qualité web | ✅ | ESLint, types générés, Playwright |
| CI/CD | ✅ CI ; déploiement non créé (INFRA-07) | `.github/workflows/ci.yml`, `.github/dependabot.yml` |

## 2. Résultats réels

| Contrôle | Résultat |
|---|---|
| Tests Python (PostgreSQL réel, lexverif) | **83 réussis**, 0 ignoré |
| Tests Rust | 22 réussis |
| Playwright (mobile Pixel 7 + ordinateur) | **6 réussis** |
| ESLint / tsc / types générés à jour | 0 avertissement / OK / OK |
| Trivy 0.75.0 (HIGH/CRITICAL corrigeables) | API **0**, web **0** (14 avant retrait de pip/npm des images d'exécution) |
| SBOM CycloneDX 1.7 | API 118 composants, web 112 |
| Test de fumée compose | ingestion 40 articles → API (rôle `avx_api`) → web → réponse vérifiée ; suppression refusée au rôle applicatif ; Keycloak : realm importé, PKCE S256, MFA TOTP imposée, politique de mot de passe |
| `terraform validate` | OK |
| checkov 3.3.26 | **452 réussis, 0 échec**, 31 exceptions motivées dans le code |
| gitleaks (historique) | aucune fuite |

## 3. Défauts trouvés par les nouveaux contrôles

1. **Privilège manquant** (test de fumée) : sous le rôle à moindre privilège,
   toute réponse échouait (`ingestion_run` illisible). L'exécution en
   propriétaire de la base masquait le défaut. Migration 0005 + test pytest
   exécutant l'API sous un rôle membre d'`avx_app`.
2. **Restauration impossible** (exercice de sauvegarde) : la vue BM25
   dépendait du `search_path`, que `pg_restore` vide. Migration 0006.
3. **Spans tiers non filtrés** (test de télémétrie) : FastAPI émet ses
   propres spans. Exportateur à liste blanche appliqué à tous les spans.
4. **Configuration Keycloak** (test de fumée) : déclarer des `clientScopes`
   supprimait les scopes par défaut. Mappeur d'audience placé sur le client.
5. **14 vulnérabilités HIGH** dans les outils d'installation des images de
   base (pip, npm) : retirés des images d'exécution.
6. **Vulnérabilité CRITIQUE** détectée par la CI (exécution n° 12) :
   `certifi` 2026.7.22, entré avec l'exportateur OpenTelemetry
   (GHSA-6q48-6c7w-9gw2, racines emSign compromises). Le contrôle bloquant a
   arrêté le job. Correction : `certifi` 2026.10.19, par exception ciblée à la
   règle des 14 jours (`exclude-newer-package`, contrainte de version
   minimale), documentée dans `pyproject.toml`.

## 4. Limites et risques

* Rien n'a été déployé : le comportement réel sur AWS (IAM, réseau, WAF) n'est
  pas éprouvé. Un premier `apply` en recette, avec données fictives, est la
  prochaine étape de validation — décision du porteur requise (coût).
* Keycloak : image officielle en mode développement localement ; une image
  optimisée et analysée est nécessaire avant recette (INFRA-08).
  L'authentification OIDC de l'API reste à implémenter (SEC-01, phase G).
* Le web joint l'API avec un jeton de service (mode développement) : il sera
  remplacé par le jeton de l'utilisateur (SEC-01).
* TLS terminé à l'ALB (cibles privées) ; chiffrement de bout en bout : SEC-11.
* Builds locaux en réseau hôte avec certificat de proxy fourni en secret
  BuildKit : propre à l'environnement de développement, sans effet sur les
  images.

## 5. Actions du porteur du projet

1. Protéger la branche `main` dans GitHub (revue obligatoire, CI requise).
2. Décider d'un premier `terraform apply` en recette : compte AWS dédié,
   budget (500 USD/mois par défaut, modifiable), domaine et certificat.

## 6. Conditions de passage à la phase C

Remplies : CI verte avec contrôles bloquants, images durcies, pile locale
testée, infrastructure validée. Non bloquant pour la phase C (corpus) : le
déploiement en recette, qui peut être mené en parallèle après décision.
