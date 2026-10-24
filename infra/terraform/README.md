# Infrastructure (Terraform)

Statut : **validée (`terraform validate`, checkov), jamais appliquée.**
Aucun `terraform apply` sans décision explicite du porteur du projet (coût,
irréversibilité ; ADR 0009). Recette : données publiques ou fictives
uniquement (DEC-01).

Région : AWS Paris `eu-west-3`.

| Module | Rôle |
|---|---|
| `kms_key` | clés KMS (rotation annuelle), usage par services nommés |
| `network` | VPC trois niveaux : public (ALB, NAT), applicatif privé (ECS), données sans route Internet (RDS) ; points de terminaison VPC ; journaux de flux |
| `database` | RDS PostgreSQL 16 : chiffré, privé, TLS obligatoire, PITR, mot de passe maître géré par Secrets Manager, aucune requête journalisée |
| `registry` | ECR : étiquettes immuables, analyse à l'envoi, KMS |
| `ecs_platform` | cluster Fargate, rôle d'exécution, découverte de services privée |
| `ecs_service` | service générique : lecture seule, non root, sans IP publique, secrets injectés |
| `edge` | ALB TLS 1.3, redirection HTTPS, WAF (règles gérées, Log4j, débit), journaux d'accès |
| `audit` | CloudTrail multi-région (événements de données sur les pièces), CloudWatch, GuardDuty |
| `budget` | budget mensuel et alertes |
| `documents_bucket`, `work_queue` | pièces client (S3 KMS) ; files SQS + DLQ |

Exposition : seuls l'application web et Keycloak sont derrière l'ALB ; l'API
est joignable uniquement depuis le web (découverte de services privée).

Contrôles : `terraform fmt -check`, `terraform validate`, checkov 3.3.26
(exceptions justifiées en commentaire `#checkov:skip=` dans le code).

Avant un premier `apply` : compte AWS dédié, bucket d'état chiffré avec
verrouillage (`backend.hcl` non versionné), certificat ACM, images dans
l'ECR du compte (INFRA-07), image Keycloak optimisée (INFRA-08), valeurs des
secrets déposées hors Terraform, `staging.tfvars` (modèle fourni).
