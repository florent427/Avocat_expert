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

variable "service_principals" {
  type        = list(string)
  default     = []
  description = "Services AWS autorisés à utiliser la clé (ex. logs.eu-west-3.amazonaws.com)"
}

data "aws_caller_identity" "current" {}

data "aws_iam_policy_document" "key" {
  #checkov:skip=CKV_AWS_111:politique de clé KMS : « * » désigne la clé elle-même ; administration réservée au compte
  #checkov:skip=CKV_AWS_356:politique de clé KMS : « * » désigne la clé elle-même
  #checkov:skip=CKV_AWS_109:politique de clé KMS : administration réservée au compte propriétaire
  statement {
    sid       = "AdministrationParLeCompte"
    actions   = ["kms:*"]
    resources = ["*"]
    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"]
    }
  }

  dynamic "statement" {
    for_each = length(var.service_principals) > 0 ? [1] : []
    content {
      sid       = "UsageParLesServices"
      actions   = ["kms:Encrypt*", "kms:Decrypt*", "kms:ReEncrypt*", "kms:GenerateDataKey*", "kms:Describe*"]
      resources = ["*"]
      principals {
        type        = "Service"
        identifiers = var.service_principals
      }
      condition {
        test     = "StringEquals"
        variable = "aws:SourceAccount"
        values   = [data.aws_caller_identity.current.account_id]
      }
    }
  }
}

resource "aws_kms_key" "this" {
  description             = var.description
  enable_key_rotation     = true
  deletion_window_in_days = var.deletion_window_in_days
  policy                  = data.aws_iam_policy_document.key.json
}

resource "aws_kms_alias" "this" {
  name          = "alias/${var.alias}"
  target_key_id = aws_kms_key.this.key_id
}

output "key_arn" {
  value = aws_kms_key.this.arn
}
