terraform {
  required_version = ">= 1.9, < 2.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.60"
    }
  }
  # Backend distant à configurer en phase B (bucket d'état + verrouillage),
  # via `terraform init -backend-config=...` : aucune valeur versionnée ici.
}

variable "project" {
  type    = string
  default = "avocat-expert"
}

variable "environment" {
  type    = string
  default = "staging"
}

provider "aws" {
  region = "eu-west-3"
  default_tags {
    tags = {
      Project     = var.project
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}

module "documents_key" {
  source      = "../../modules/kms_key"
  alias       = "${var.project}-${var.environment}-documents"
  description = "Chiffrement des pièces client (${var.environment})"
}

module "documents_bucket" {
  source      = "../../modules/documents_bucket"
  name        = "${var.project}-${var.environment}-documents"
  kms_key_arn = module.documents_key.key_arn
}

module "ingestion_queue" {
  source      = "../../modules/work_queue"
  name        = "${var.project}-${var.environment}-ingestion"
  kms_key_arn = module.documents_key.key_arn
}
