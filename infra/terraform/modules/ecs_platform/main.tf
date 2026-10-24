# Socle ECS Fargate : cluster, rôle d'exécution, découverte de services privée.

variable "name" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "secret_arns" {
  type        = list(string)
  description = "Secrets que le rôle d'exécution peut injecter dans les conteneurs"
}

variable "kms_key_arns" {
  type = list(string)
}

resource "aws_ecs_cluster" "this" {
  name = var.name
  setting {
    name  = "containerInsights"
    value = "enabled"
  }
}

data "aws_iam_policy_document" "ecs_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "execution" {
  name               = "${var.name}-ecs-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

resource "aws_iam_role_policy_attachment" "execution" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

data "aws_iam_policy_document" "execution_secrets" {
  statement {
    actions   = ["secretsmanager:GetSecretValue"]
    resources = var.secret_arns
  }
  statement {
    actions   = ["kms:Decrypt"]
    resources = var.kms_key_arns
  }
}

resource "aws_iam_role_policy" "execution_secrets" {
  role   = aws_iam_role.execution.id
  policy = data.aws_iam_policy_document.execution_secrets.json
}

resource "aws_service_discovery_private_dns_namespace" "this" {
  name = "${var.name}.internal"
  vpc  = var.vpc_id
}

output "cluster_arn" {
  value = aws_ecs_cluster.this.arn
}

output "execution_role_arn" {
  value = aws_iam_role.execution.arn
}

output "namespace_id" {
  value = aws_service_discovery_private_dns_namespace.this.id
}

output "namespace_name" {
  value = aws_service_discovery_private_dns_namespace.this.name
}

output "task_assume_role_policy" {
  value = data.aws_iam_policy_document.ecs_assume.json
}
