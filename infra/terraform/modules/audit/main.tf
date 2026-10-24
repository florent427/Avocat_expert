# Traçabilité du compte : CloudTrail (toutes régions, validation d'intégrité,
# chiffrement KMS) et détection des menaces (GuardDuty).

variable "name" {
  type = string
}

variable "kms_key_arn" {
  type        = string
  description = "Clé autorisant cloudtrail.amazonaws.com et logs"
}

variable "data_event_bucket_arns" {
  type        = list(string)
  default     = []
  description = "Compartiments dont chaque accès aux objets est tracé (pièces client)"
}

data "aws_caller_identity" "current" {}

resource "aws_s3_bucket" "trail" {
  #checkov:skip=CKV_AWS_18:compartiment de journaux d'audit ; pas de journalisation récursive
  #checkov:skip=CKV2_AWS_62:compartiment de journaux, sans traitement événementiel
  #checkov:skip=CKV_AWS_144:pas de réplication inter-région (hébergement en France)
  bucket = "${var.name}-cloudtrail"
}

resource "aws_s3_bucket_lifecycle_configuration" "trail" {
  bucket = aws_s3_bucket.trail.id
  rule {
    id     = "versions-remplacees"
    status = "Enabled"
    filter {}
    noncurrent_version_expiration {
      noncurrent_days = 90
    }
    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}

resource "aws_cloudwatch_log_group" "trail" {
  name              = "/avx/${var.name}/cloudtrail"
  retention_in_days = 365
  kms_key_id        = var.kms_key_arn
}

data "aws_iam_policy_document" "trail_logs_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["cloudtrail.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "trail_logs" {
  name               = "${var.name}-cloudtrail-logs"
  assume_role_policy = data.aws_iam_policy_document.trail_logs_assume.json
}

data "aws_iam_policy_document" "trail_logs" {
  statement {
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.trail.arn}:*"]
  }
}

resource "aws_iam_role_policy" "trail_logs" {
  role   = aws_iam_role.trail_logs.id
  policy = data.aws_iam_policy_document.trail_logs.json
}

resource "aws_s3_bucket_public_access_block" "trail" {
  bucket                  = aws_s3_bucket.trail.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "trail" {
  bucket = aws_s3_bucket.trail.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "trail" {
  bucket = aws_s3_bucket.trail.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = var.kms_key_arn
    }
    bucket_key_enabled = true
  }
}

data "aws_iam_policy_document" "trail" {
  statement {
    sid       = "CloudTrailAclCheck"
    actions   = ["s3:GetBucketAcl"]
    resources = [aws_s3_bucket.trail.arn]
    principals {
      type        = "Service"
      identifiers = ["cloudtrail.amazonaws.com"]
    }
  }
  statement {
    sid       = "CloudTrailWrite"
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.trail.arn}/AWSLogs/${data.aws_caller_identity.current.account_id}/*"]
    principals {
      type        = "Service"
      identifiers = ["cloudtrail.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "s3:x-amz-acl"
      values   = ["bucket-owner-full-control"]
    }
  }
  statement {
    sid       = "DenyInsecureTransport"
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = [aws_s3_bucket.trail.arn, "${aws_s3_bucket.trail.arn}/*"]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "trail" {
  bucket = aws_s3_bucket.trail.id
  policy = data.aws_iam_policy_document.trail.json
}

resource "aws_cloudtrail" "this" {
  #checkov:skip=CKV_AWS_252:alertes portées par GuardDuty et EventBridge (backlog SEC-12), pas par une notification par fichier de journal
  name                          = var.name
  s3_bucket_name                = aws_s3_bucket.trail.id
  is_multi_region_trail         = true
  include_global_service_events = true
  enable_log_file_validation    = true
  kms_key_id                    = var.kms_key_arn
  cloud_watch_logs_group_arn    = "${aws_cloudwatch_log_group.trail.arn}:*"
  cloud_watch_logs_role_arn     = aws_iam_role.trail_logs.arn

  dynamic "event_selector" {
    for_each = length(var.data_event_bucket_arns) > 0 ? [1] : []
    content {
      read_write_type           = "All"
      include_management_events = true
      data_resource {
        type   = "AWS::S3::Object"
        values = [for arn in var.data_event_bucket_arns : "${arn}/"]
      }
    }
  }

  depends_on = [aws_s3_bucket_policy.trail]
}

resource "aws_guardduty_detector" "this" {
  #checkov:skip=CKV2_AWS_3:compte unique à ce stade ; activation au niveau de l'organisation AWS lorsqu'elle existera
  enable = true
}
