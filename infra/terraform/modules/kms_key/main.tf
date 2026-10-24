variable "alias" {
  type        = string
  description = "Alias KMS (sans le préfixe alias/)"
}

variable "description" {
  type = string
}

variable "deletion_window_in_days" {
  type    = number
  default = 30
}

resource "aws_kms_key" "this" {
  description             = var.description
  enable_key_rotation     = true
  deletion_window_in_days = var.deletion_window_in_days
}

resource "aws_kms_alias" "this" {
  name          = "alias/${var.alias}"
  target_key_id = aws_kms_key.this.key_id
}

output "key_arn" {
  value = aws_kms_key.this.arn
}
