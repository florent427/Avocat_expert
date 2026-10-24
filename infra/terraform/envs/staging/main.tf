terraform {
  required_version = ">= 1.9, < 2.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.60"
    }
  }
  # Backend distant (bucket d'état chiffré + verrouillage) configuré au moment
  # de l'initialisation : `terraform init -backend-config=backend.hcl`.
  # Aucune valeur n'est versionnée ici.
  backend "s3" {}
}

provider "aws" {
  region = "eu-west-3"
  default_tags {
    tags = {
      Project     = var.project
      Environment = var.environment
      ManagedBy   = "terraform"
      DataClass   = "fictive-uniquement" # DEC-01 : aucune donnée client réelle en recette
    }
  }
}

data "aws_region" "current" {}

locals {
  name   = "${var.project}-${var.environment}"
  region = data.aws_region.current.region
}

# --- Chiffrement ---------------------------------------------------------

module "data_key" {
  source      = "../../modules/kms_key"
  alias       = "${local.name}-data"
  description = "Données (${var.environment}) : base, pièces, files, secrets"
}

module "logs_key" {
  source      = "../../modules/kms_key"
  alias       = "${local.name}-logs"
  description = "Journaux et audit (${var.environment})"
  service_principals = [
    "logs.${local.region}.amazonaws.com",
    "cloudtrail.amazonaws.com",
  ]
}

# --- Réseau --------------------------------------------------------------

module "network" {
  source            = "../../modules/network"
  name              = local.name
  azs               = ["eu-west-3a", "eu-west-3b"]
  nat_gateway_count = 1
  logs_kms_key_arn  = module.logs_key.key_arn
}

resource "aws_security_group" "web" {
  #checkov:skip=CKV2_AWS_5:rattaché aux services ECS et à RDS via les modules (faux positif inter-modules)
  name        = "${local.name}-web"
  description = "Application web : depuis l'ALB"
  vpc_id      = module.network.vpc_id
}

resource "aws_security_group" "auth" {
  #checkov:skip=CKV2_AWS_5:rattaché aux services ECS et à RDS via les modules (faux positif inter-modules)
  name        = "${local.name}-auth"
  description = "Keycloak : depuis l'ALB et l'API"
  vpc_id      = module.network.vpc_id
}

resource "aws_security_group" "api" {
  #checkov:skip=CKV2_AWS_5:rattaché aux services ECS et à RDS via les modules (faux positif inter-modules)
  name        = "${local.name}-api"
  description = "API : depuis l'application web uniquement"
  vpc_id      = module.network.vpc_id
}

resource "aws_security_group" "jobs" {
  #checkov:skip=CKV2_AWS_5:rattaché aux services ECS et à RDS via les modules (faux positif inter-modules)
  name        = "${local.name}-jobs"
  description = "Tâches ponctuelles (migrations, ingestion)"
  vpc_id      = module.network.vpc_id
}

resource "aws_vpc_security_group_ingress_rule" "web_from_alb" {
  description                  = "Web depuis l'ALB"
  security_group_id            = aws_security_group.web.id
  referenced_security_group_id = module.edge.alb_security_group_id
  ip_protocol                  = "tcp"
  from_port                    = 3000
  to_port                      = 3000
}

resource "aws_vpc_security_group_ingress_rule" "auth_from_alb" {
  description                  = "Keycloak depuis l'ALB"
  security_group_id            = aws_security_group.auth.id
  referenced_security_group_id = module.edge.alb_security_group_id
  ip_protocol                  = "tcp"
  from_port                    = 8080
  to_port                      = 8080
}

resource "aws_vpc_security_group_ingress_rule" "api_from_web" {
  description                  = "API depuis le web"
  security_group_id            = aws_security_group.api.id
  referenced_security_group_id = aws_security_group.web.id
  ip_protocol                  = "tcp"
  from_port                    = 8000
  to_port                      = 8000
}

# Sorties : HTTPS (points de terminaison AWS, sources officielles) et
# PostgreSQL vers le VPC. Rien d'autre.
resource "aws_vpc_security_group_egress_rule" "https" {
  for_each          = { web = aws_security_group.web.id, auth = aws_security_group.auth.id, api = aws_security_group.api.id, jobs = aws_security_group.jobs.id }
  security_group_id = each.value
  description       = "HTTPS sortant"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
}

resource "aws_vpc_security_group_egress_rule" "postgres" {
  for_each          = { auth = aws_security_group.auth.id, api = aws_security_group.api.id, jobs = aws_security_group.jobs.id }
  security_group_id = each.value
  description       = "PostgreSQL dans le VPC"
  cidr_ipv4         = module.network.vpc_cidr
  ip_protocol       = "tcp"
  from_port         = 5432
  to_port           = 5432
}

resource "aws_vpc_security_group_egress_rule" "web_to_api" {
  description                  = "Web vers API"
  security_group_id            = aws_security_group.web.id
  referenced_security_group_id = aws_security_group.api.id
  ip_protocol                  = "tcp"
  from_port                    = 8000
  to_port                      = 8000
}

resource "aws_vpc_security_group_egress_rule" "alb_to_targets" {
  for_each                     = { web = { sg = aws_security_group.web.id, port = 3000 }, auth = { sg = aws_security_group.auth.id, port = 8080 } }
  description                  = "ALB vers ${each.key}"
  security_group_id            = module.edge.alb_security_group_id
  referenced_security_group_id = each.value.sg
  ip_protocol                  = "tcp"
  from_port                    = each.value.port
  to_port                      = each.value.port
}

# --- Données -------------------------------------------------------------

module "database" {
  source                    = "../../modules/database"
  name                      = local.name
  vpc_id                    = module.network.vpc_id
  subnet_ids                = module.network.data_subnet_ids
  client_security_group_ids = [aws_security_group.api.id, aws_security_group.auth.id, aws_security_group.jobs.id]
  kms_key_arn               = module.data_key.key_arn
  multi_az                  = false # recette sans données réelles ; true en production
  backup_retention_days     = 14
}

module "documents_bucket" {
  source      = "../../modules/documents_bucket"
  name        = "${local.name}-documents"
  kms_key_arn = module.data_key.key_arn
}

module "ingestion_queue" {
  source      = "../../modules/work_queue"
  name        = "${local.name}-ingestion"
  kms_key_arn = module.data_key.key_arn
}

# Secrets créés vides : les valeurs sont déposées hors Terraform (procédure
# d'exploitation) et n'apparaissent jamais dans l'état.
resource "aws_secretsmanager_secret" "this" {
  #checkov:skip=CKV2_AWS_57:rotation à mettre en place avec la procédure d'exploitation (backlog SEC-10) ; le secret maître RDS est géré et tourné par RDS
  for_each   = toset(["api-database-url", "keycloak-database-password", "keycloak-admin"])
  name       = "${local.name}/${each.value}"
  kms_key_id = module.data_key.key_arn
}

# --- Images --------------------------------------------------------------

module "registry" {
  source       = "../../modules/registry"
  repositories = ["${var.project}/api", "${var.project}/web", "${var.project}/keycloak"]
  kms_key_arn  = module.data_key.key_arn
}

# --- Exécution -----------------------------------------------------------

module "platform" {
  source       = "../../modules/ecs_platform"
  name         = local.name
  vpc_id       = module.network.vpc_id
  secret_arns  = concat([for s in aws_secretsmanager_secret.this : s.arn], [module.database.master_secret_arn])
  kms_key_arns = [module.data_key.key_arn]
}

locals {
  service_defaults = {
    cluster_arn             = module.platform.cluster_arn
    execution_role_arn      = module.platform.execution_role_arn
    task_assume_role_policy = module.platform.task_assume_role_policy
    subnet_ids              = module.network.app_subnet_ids
    logs_kms_key_arn        = module.logs_key.key_arn
  }
  api_image      = "${module.registry.repository_urls["${var.project}/api"]}:${var.image_tag}"
  web_image      = "${module.registry.repository_urls["${var.project}/web"]}:${var.image_tag}"
  keycloak_image = "${module.registry.repository_urls["${var.project}/keycloak"]}:${var.image_tag}"
  api_env = {
    AVX_ENVIRONMENT            = var.environment
    AVX_AUTH_MODE              = "oidc"
    AVX_OIDC_ISSUER            = "https://${var.auth_host}/realms/avocat-expert"
    AVX_OIDC_AUDIENCE          = "avocat-expert-api"
    AVX_OTEL_EXPORTER_ENDPOINT = var.otel_exporter_endpoint
  }
  api_secrets = { AVX_DATABASE_URL = aws_secretsmanager_secret.this["api-database-url"].arn }
}

module "api" {
  source                         = "../../modules/ecs_service"
  name                           = "${local.name}-api"
  image                          = local.api_image
  container_port                 = 8000
  environment                    = local.api_env
  secrets                        = local.api_secrets
  security_group_ids             = [aws_security_group.api.id]
  service_discovery_namespace_id = module.platform.namespace_id
  cluster_arn                    = local.service_defaults.cluster_arn
  execution_role_arn             = local.service_defaults.execution_role_arn
  task_assume_role_policy        = local.service_defaults.task_assume_role_policy
  subnet_ids                     = local.service_defaults.subnet_ids
  logs_kms_key_arn               = local.service_defaults.logs_kms_key_arn
}

module "migrate" {
  source                  = "../../modules/ecs_service"
  name                    = "${local.name}-migrate"
  image                   = local.api_image
  command                 = ["avx", "migrate"]
  run_as_service          = false
  environment             = { AVX_ENVIRONMENT = var.environment }
  secrets                 = { AVX_DATABASE_URL = "${module.database.master_secret_arn}:url::" }
  security_group_ids      = [aws_security_group.jobs.id]
  cluster_arn             = local.service_defaults.cluster_arn
  execution_role_arn      = local.service_defaults.execution_role_arn
  task_assume_role_policy = local.service_defaults.task_assume_role_policy
  subnet_ids              = local.service_defaults.subnet_ids
  logs_kms_key_arn        = local.service_defaults.logs_kms_key_arn
}

module "web" {
  source           = "../../modules/ecs_service"
  name             = "${local.name}-web"
  image            = local.web_image
  container_port   = 3000
  user             = "1000:1000"
  writable_paths   = ["/app/.next/cache"]
  environment      = { AVX_API_URL = "http://${local.name}-api.${module.platform.namespace_name}:8000" }
  target_group_arn = module.edge.web_target_group_arn
  # AVX_API_TOKEN disparaît avec l'OIDC (SEC-01) : le web transmettra le jeton de l'utilisateur.
  security_group_ids      = [aws_security_group.web.id]
  cluster_arn             = local.service_defaults.cluster_arn
  execution_role_arn      = local.service_defaults.execution_role_arn
  task_assume_role_policy = local.service_defaults.task_assume_role_policy
  subnet_ids              = local.service_defaults.subnet_ids
  logs_kms_key_arn        = local.service_defaults.logs_kms_key_arn
}

module "keycloak" {
  source         = "../../modules/ecs_service"
  name           = "${local.name}-keycloak"
  image          = local.keycloak_image
  command        = ["start", "--optimized"]
  container_port = 8080
  user           = "1000:0"
  cpu            = 1024
  memory         = 2048
  writable_paths = ["/opt/keycloak/data", "/tmp"]
  environment = {
    KC_DB              = "postgres"
    KC_DB_URL          = "jdbc:postgresql://${module.database.endpoint}:5432/keycloak?sslmode=require"
    KC_DB_USERNAME     = "keycloak"
    KC_HOSTNAME        = "https://${var.auth_host}"
    KC_PROXY_HEADERS   = "xforwarded"
    KC_HTTP_ENABLED    = "true"
    KC_HEALTH_ENABLED  = "true"
    KC_METRICS_ENABLED = "true"
  }
  secrets = {
    KC_DB_PASSWORD              = aws_secretsmanager_secret.this["keycloak-database-password"].arn
    KC_BOOTSTRAP_ADMIN_USERNAME = "${aws_secretsmanager_secret.this["keycloak-admin"].arn}:username::"
    KC_BOOTSTRAP_ADMIN_PASSWORD = "${aws_secretsmanager_secret.this["keycloak-admin"].arn}:password::"
  }
  target_group_arn        = module.edge.auth_target_group_arn
  security_group_ids      = [aws_security_group.auth.id]
  cluster_arn             = local.service_defaults.cluster_arn
  execution_role_arn      = local.service_defaults.execution_role_arn
  task_assume_role_policy = local.service_defaults.task_assume_role_policy
  subnet_ids              = local.service_defaults.subnet_ids
  logs_kms_key_arn        = local.service_defaults.logs_kms_key_arn
}

# --- Exposition, audit, coûts --------------------------------------------

module "edge" {
  source            = "../../modules/edge"
  name              = local.name
  vpc_id            = module.network.vpc_id
  public_subnet_ids = module.network.public_subnet_ids
  certificate_arn   = var.certificate_arn
  app_host          = var.app_host
  auth_host         = var.auth_host
  logs_kms_key_arn  = module.logs_key.key_arn
}

module "audit" {
  source                 = "../../modules/audit"
  name                   = local.name
  kms_key_arn            = module.logs_key.key_arn
  data_event_bucket_arns = [module.documents_bucket.bucket_arn]
}

module "budget" {
  source            = "../../modules/budget"
  name              = local.name
  monthly_limit_usd = var.monthly_budget_usd
  alert_emails      = var.budget_alert_emails
}
