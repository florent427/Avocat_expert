# ADR 0014 — Conteneurs et chaîne d'approvisionnement

**Statut** : proposée — implémentée · 2026-10-24

## Décision
* Images de base servies par la galerie publique ECR (miroir officiel des
  images Docker ; évite les limites anonymes de Docker Hub), **épinglées par
  empreinte** ; pgvector via `mirror.gcr.io`, Keycloak via `quay.io`
  (image officielle), à recopier dans l'ECR du compte avant production.
* Images d'exécution sans outils d'installation (pip, npm, corepack, yarn
  retirés), utilisateur non privilégié, système de fichiers en lecture seule
  (compose et ECS), capacités Linux retirées.
* Chaque push : construction, analyse Trivy (échec sur toute vulnérabilité
  HIGH/CRITICAL corrigeable), SBOM CycloneDX en artefact, test de fumée de la
  pile complète.
* Dépendances : versions exactes, ancienneté minimale de 14 jours
  (`uv exclude-newer`, Dependabot `cooldown`), exception documentée pour les
  correctifs de sécurité ; actions GitHub épinglées par SHA ; binaires
  d'outillage (gitleaks, Trivy) vérifiés par somme de contrôle.
* Signature des images (cosign) et attestation de provenance : à la mise en
  place du registre ECR et du déploiement (backlog INFRA-07).
