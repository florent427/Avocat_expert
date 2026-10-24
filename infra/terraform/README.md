# Infrastructure (Terraform) — socle initial

Statut : **squelette validé syntaxiquement (`terraform validate`), jamais
appliqué**. Aucun `terraform apply` ne doit être lancé sans validation
explicite (coût, irréversibilité, conformité) — voir ADR 0009.

Région cible : AWS Paris `eu-west-3`.

| Module | Rôle |
|---|---|
| `modules/kms_key` | clé KMS dédiée (rotation annuelle activée) |
| `modules/documents_bucket` | bucket S3 des pièces client : chiffrement SSE-KMS, accès public bloqué, versionnement, TLS obligatoire, propriété des objets imposée |
| `modules/work_queue` | file SQS chiffrée KMS + file de lettres mortes |

À venir (backlog INFRA-*) : réseau (VPC privé, endpoints VPC, pas d'IGW
pour les tâches), RDS PostgreSQL (chiffré, sauvegardes, PITR), OpenSearch,
ECS Fargate, ALB + WAF, Secrets Manager, CloudTrail, GuardDuty, budgets.

L'état distant (S3 + verrouillage) sera configuré lors de la phase B, avec un
compte AWS dédié. Les identifiants ne sont jamais versionnés.
