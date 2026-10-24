# PostgreSQL 16 managé (RDS) : chiffré, privé, TLS obligatoire, sauvegardes
# et restauration à un instant donné, mot de passe maître géré par Secrets
# Manager (jamais présent dans l'état Terraform).

variable "name" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "subnet_ids" {
  type = list(string)
}

variable "client_security_group_ids" {
  type        = list(string)
  description = "Groupes de sécurité autorisés à joindre la base (tâches ECS)"
}

variable "kms_key_arn" {
  type = string
}

variable "instance_class" {
  type    = string
  default = "db.t4g.medium"
}

variable "allocated_storage" {
  type    = number
  default = 50
}

variable "multi_az" {
  type    = bool
  default = false
}

variable "backup_retention_days" {
  type    = number
  default = 14
}

resource "aws_db_subnet_group" "this" {
  name       = var.name
  subnet_ids = var.subnet_ids
}

resource "aws_security_group" "db" {
  name        = "${var.name}-db"
  description = "PostgreSQL : accès depuis les tâches applicatives uniquement"
  vpc_id      = var.vpc_id
}

resource "aws_vpc_security_group_ingress_rule" "db" {
  for_each                     = toset(var.client_security_group_ids)
  security_group_id            = aws_security_group.db.id
  description                  = "PostgreSQL depuis ${each.value}"
  referenced_security_group_id = each.value
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
}

resource "aws_db_parameter_group" "this" {
  name   = var.name
  family = "postgres16"

  parameter {
    name  = "rds.force_ssl"
    value = "1"
  }
  # Aucune requête journalisée en clair (elles peuvent contenir des données client).
  parameter {
    name  = "log_statement"
    value = "none"
  }
  parameter {
    name  = "log_min_duration_statement"
    value = "-1"
  }
}

data "aws_iam_policy_document" "monitoring_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["monitoring.rds.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "monitoring" {
  name               = "${var.name}-rds-monitoring"
  assume_role_policy = data.aws_iam_policy_document.monitoring_assume.json
}

resource "aws_iam_role_policy_attachment" "monitoring" {
  role       = aws_iam_role.monitoring.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonRDSEnhancedMonitoringRole"
}

resource "aws_db_instance" "this" {
  #checkov:skip=CKV_AWS_157:Multi-AZ paramétré (var.multi_az) : désactivé en recette sans données réelles, activé en production
  identifier                          = var.name
  engine                              = "postgres"
  engine_version                      = "16"
  instance_class                      = var.instance_class
  allocated_storage                   = var.allocated_storage
  max_allocated_storage               = var.allocated_storage * 4
  storage_type                        = "gp3"
  storage_encrypted                   = true
  kms_key_id                          = var.kms_key_arn
  db_name                             = "avocat_expert"
  username                            = "avx_owner"
  manage_master_user_password         = true
  master_user_secret_kms_key_id       = var.kms_key_arn
  iam_database_authentication_enabled = true
  db_subnet_group_name                = aws_db_subnet_group.this.name
  vpc_security_group_ids              = [aws_security_group.db.id]
  parameter_group_name                = aws_db_parameter_group.this.name
  publicly_accessible                 = false
  multi_az                            = var.multi_az
  backup_retention_period             = var.backup_retention_days
  backup_window                       = "01:00-02:00"
  maintenance_window                  = "sun:03:00-sun:04:00"
  copy_tags_to_snapshot               = true
  deletion_protection                 = true
  skip_final_snapshot                 = false
  final_snapshot_identifier           = "${var.name}-final"
  auto_minor_version_upgrade          = true
  performance_insights_enabled        = true
  performance_insights_kms_key_id     = var.kms_key_arn
  monitoring_interval                 = 60
  monitoring_role_arn                 = aws_iam_role.monitoring.arn
  enabled_cloudwatch_logs_exports     = ["postgresql"]
}

output "endpoint" {
  value = aws_db_instance.this.address
}

output "master_secret_arn" {
  value = aws_db_instance.this.master_user_secret[0].secret_arn
}
