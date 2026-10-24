# ADR 0009 — AWS eu-west-3, Terraform, aucun apply sans validation

**Statut** : acceptée le 2026-10-24 (voir `docs/decisions/registre-decisions.md`)

## Décision
* Région AWS Paris `eu-west-3`, services managés (ECS Fargate, RDS, S3, SQS,
  OpenSearch, KMS, Secrets Manager), Terraform, état distant chiffré.
* Aucun `terraform apply`, aucune création de compte ou ressource payante
  sans validation explicite du porteur du projet.

## Question ouverte (bloquante pour la production)
AWS est une société de droit américain. Les dossiers d'avocats relèvent du
secret professionnel. La compatibilité de cet hébergement avec les
exigences du secret professionnel, du RGPD (transferts, accès d'autorités
étrangères) et des attentes des ordres doit être évaluée par le DPO et un
conseil spécialisé ; une alternative qualifiée SecNumCloud doit être
chiffrée. L'abstraction des services (S3 compatible, PostgreSQL, conteneurs)
préserve la réversibilité.

## Amendement du 2026-10-24 (DEC-01)
AWS eu-west-3 est retenu pour le développement et la recette **avec des
données publiques ou fictives uniquement**. L'hébergement de production
(AWS, hybride ou SecNumCloud) sera décidé après avis du DPO et d'un conseil.
D'ici là, aucun choix ne doit lier l'application à un service propre à AWS
sans équivalent chez un hébergeur qualifié (objet S3 compatible, PostgreSQL,
conteneurs OCI, Keycloak, files de messages abstraites derrière un port).
