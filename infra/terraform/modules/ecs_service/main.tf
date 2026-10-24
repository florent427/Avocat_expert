# Service ECS Fargate générique : système de fichiers racine en lecture
# seule, utilisateur non privilégié, aucune adresse publique, secrets
# injectés depuis Secrets Manager, journaux chiffrés.

variable "name" {
  type = string
}

variable "cluster_arn" {
  type = string
}

variable "execution_role_arn" {
  type = string
}

variable "task_assume_role_policy" {
  type = string
}

variable "task_policy_json" {
  type        = string
  default     = ""
  description = "Politique IAM propre à la tâche (vide = aucun droit AWS)"
}

variable "image" {
  type = string
}

variable "command" {
  type    = list(string)
  default = null
}

variable "container_port" {
  type    = number
  default = null
}

variable "user" {
  type    = string
  default = "10001:10001"
}

variable "cpu" {
  type    = number
  default = 512
}

variable "memory" {
  type    = number
  default = 1024
}

variable "desired_count" {
  type    = number
  default = 1
}

variable "environment" {
  type    = map(string)
  default = {}
}

variable "secrets" {
  type        = map(string)
  default     = {}
  description = "Nom de variable -> ARN du secret (ou ARN:clé::)"
}

variable "writable_paths" {
  type        = list(string)
  default     = []
  description = "Répertoires montés en volume éphémère inscriptible"
}

variable "subnet_ids" {
  type = list(string)
}

variable "security_group_ids" {
  type = list(string)
}

variable "logs_kms_key_arn" {
  type = string
}

variable "target_group_arn" {
  type    = string
  default = ""
}

variable "service_discovery_namespace_id" {
  type    = string
  default = ""
}

variable "run_as_service" {
  type        = bool
  default     = true
  description = "false : définition de tâche seule (tâche ponctuelle, ex. migrations)"
}

data "aws_region" "current" {}

resource "aws_cloudwatch_log_group" "this" {
  name              = "/avx/ecs/${var.name}"
  retention_in_days = 365
  kms_key_id        = var.logs_kms_key_arn
}

resource "aws_iam_role" "task" {
  name               = "${var.name}-task"
  assume_role_policy = var.task_assume_role_policy
}

resource "aws_iam_role_policy" "task" {
  count  = var.task_policy_json == "" ? 0 : 1
  role   = aws_iam_role.task.id
  policy = var.task_policy_json
}

resource "aws_ecs_task_definition" "this" {
  family                   = var.name
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = var.cpu
  memory                   = var.memory
  execution_role_arn       = var.execution_role_arn
  task_role_arn            = aws_iam_role.task.arn
  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  dynamic "volume" {
    for_each = var.writable_paths
    content {
      name = "scratch-${volume.key}"
    }
  }

  container_definitions = jsonencode([{
    name                   = var.name
    image                  = var.image
    essential              = true
    command                = var.command
    user                   = var.user
    readonlyRootFilesystem = true
    privileged             = false
    linuxParameters        = { capabilities = { drop = ["ALL"] }, initProcessEnabled = true }
    portMappings           = var.container_port == null ? [] : [{ containerPort = var.container_port, protocol = "tcp" }]
    environment            = [for k, v in var.environment : { name = k, value = v }]
    secrets                = [for k, v in var.secrets : { name = k, valueFrom = v }]
    mountPoints            = [for i, p in var.writable_paths : { sourceVolume = "scratch-${i}", containerPath = p, readOnly = false }]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.this.name
        awslogs-region        = data.aws_region.current.region
        awslogs-stream-prefix = var.name
      }
    }
  }])
}

resource "aws_service_discovery_service" "this" {
  count = var.run_as_service && var.service_discovery_namespace_id != "" ? 1 : 0
  name  = var.name
  dns_config {
    namespace_id   = var.service_discovery_namespace_id
    routing_policy = "MULTIVALUE"
    dns_records {
      type = "A"
      ttl  = 10
    }
  }
}

resource "aws_ecs_service" "this" {
  count                  = var.run_as_service ? 1 : 0
  name                   = var.name
  cluster                = var.cluster_arn
  task_definition        = aws_ecs_task_definition.this.arn
  desired_count          = var.desired_count
  launch_type            = "FARGATE"
  enable_execute_command = false
  propagate_tags         = "SERVICE"

  network_configuration {
    subnets          = var.subnet_ids
    security_groups  = var.security_group_ids
    assign_public_ip = false
  }

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  dynamic "load_balancer" {
    for_each = var.target_group_arn == "" ? [] : [1]
    content {
      target_group_arn = var.target_group_arn
      container_name   = var.name
      container_port   = var.container_port
    }
  }

  dynamic "service_registries" {
    for_each = aws_service_discovery_service.this
    content {
      registry_arn = service_registries.value.arn
    }
  }
}

output "task_definition_arn" {
  value = aws_ecs_task_definition.this.arn
}

output "task_role_name" {
  value = aws_iam_role.task.name
}
