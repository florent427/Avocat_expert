variable "name" {
  type = string
}

variable "kms_key_arn" {
  type = string
}

resource "aws_s3_bucket" "this" {
  #checkov:skip=CKV_AWS_18:accès journalisés par les événements de données CloudTrail (module audit), plus précis que les journaux d'accès S3
  #checkov:skip=CKV2_AWS_62:notifications ajoutées avec l'analyse antivirale des pièces (backlog SEC-04)
  #checkov:skip=CKV_AWS_144:pas de réplication inter-région : données hébergées en France (eu-west-3) ; sauvegarde par versionnement
  bucket = var.name
}

resource "aws_s3_bucket_lifecycle_configuration" "this" {
  bucket = aws_s3_bucket.this.id
  rule {
    id     = "versions-et-envois-incomplets"
    status = "Enabled"
    filter {}
    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
    # La conservation des pièces relève de la politique de chaque cabinet ;
    # les versions remplacées ou effacées sont purgées après 30 jours.
    noncurrent_version_expiration {
      noncurrent_days = 30
    }
  }
}

resource "aws_s3_bucket_public_access_block" "this" {
  bucket                  = aws_s3_bucket.this.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "this" {
  bucket = aws_s3_bucket.this.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_versioning" "this" {
  bucket = aws_s3_bucket.this.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "this" {
  bucket = aws_s3_bucket.this.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = var.kms_key_arn
    }
    bucket_key_enabled = true
  }
}

data "aws_iam_policy_document" "tls_only" {
  statement {
    sid     = "DenyInsecureTransport"
    effect  = "Deny"
    actions = ["s3:*"]
    resources = [
      aws_s3_bucket.this.arn,
      "${aws_s3_bucket.this.arn}/*",
    ]
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

resource "aws_s3_bucket_policy" "this" {
  bucket = aws_s3_bucket.this.id
  policy = data.aws_iam_policy_document.tls_only.json
}

output "bucket_arn" {
  value = aws_s3_bucket.this.arn
}
