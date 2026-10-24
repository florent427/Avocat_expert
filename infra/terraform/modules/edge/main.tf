# Exposition : ALB public en HTTPS (TLS 1.2 minimum, 1.3 préféré),
# redirection HTTP -> HTTPS, WAF (règles gérées AWS + limitation de débit).
# Seules l'application web et Keycloak sont exposées ; l'API reste privée.

variable "name" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "public_subnet_ids" {
  type = list(string)
}

variable "certificate_arn" {
  type        = string
  description = "Certificat ACM (eu-west-3) couvrant app_host et auth_host"
}

variable "app_host" {
  type = string
}

variable "auth_host" {
  type = string
}

variable "logs_kms_key_arn" {
  type = string
}

variable "rate_limit_per_5min" {
  type    = number
  default = 1000
}

resource "aws_security_group" "alb" {
  name        = "${var.name}-alb"
  description = "ALB public : HTTP/HTTPS entrants"
  vpc_id      = var.vpc_id
}

resource "aws_vpc_security_group_ingress_rule" "alb" {
  #checkov:skip=CKV_AWS_260:le port 80 ne sert qu'à rediriger vers HTTPS (écouteur « redirect »)
  for_each          = toset(["80", "443"])
  security_group_id = aws_security_group.alb.id
  description       = "Port ${each.value} depuis Internet"
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = tonumber(each.value)
  to_port           = tonumber(each.value)
}

# Journaux d'accès de l'ALB (chiffrement SSE-S3 : seul mode accepté par ELB).
resource "aws_s3_bucket" "alb_logs" {
  #checkov:skip=CKV_AWS_145:les journaux d'accès ELB n'acceptent que le chiffrement SSE-S3
  #checkov:skip=CKV_AWS_18:compartiment de journaux ; pas de journalisation récursive
  #checkov:skip=CKV2_AWS_62:compartiment de journaux, sans traitement événementiel
  #checkov:skip=CKV_AWS_144:pas de réplication inter-région (hébergement en France)
  bucket = "${var.name}-alb-logs"
}

resource "aws_s3_bucket_public_access_block" "alb_logs" {
  bucket                  = aws_s3_bucket.alb_logs.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "alb_logs" {
  bucket = aws_s3_bucket.alb_logs.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "alb_logs" {
  bucket = aws_s3_bucket.alb_logs.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "alb_logs" {
  bucket = aws_s3_bucket.alb_logs.id
  rule {
    id     = "conservation-un-an"
    status = "Enabled"
    filter {}
    expiration {
      days = 365
    }
    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
    noncurrent_version_expiration {
      noncurrent_days = 30
    }
  }
}

data "aws_iam_policy_document" "alb_logs" {
  statement {
    sid       = "LivraisonJournauxELB"
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.alb_logs.arn}/AWSLogs/*"]
    principals {
      type        = "Service"
      identifiers = ["logdelivery.elasticloadbalancing.amazonaws.com"]
    }
  }
  statement {
    sid       = "DenyInsecureTransport"
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = [aws_s3_bucket.alb_logs.arn, "${aws_s3_bucket.alb_logs.arn}/*"]
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

resource "aws_s3_bucket_policy" "alb_logs" {
  bucket = aws_s3_bucket.alb_logs.id
  policy = data.aws_iam_policy_document.alb_logs.json
}

resource "aws_lb" "this" {
  #checkov:skip=CKV2_AWS_76:protection Log4j assurée par AWSManagedRulesKnownBadInputsRuleSet ; la liste AnonymousIpList exigée en plus bloquerait les avocats travaillant derrière un VPN légitime
  name                       = var.name
  load_balancer_type         = "application"
  internal                   = false
  subnets                    = var.public_subnet_ids
  security_groups            = [aws_security_group.alb.id]
  drop_invalid_header_fields = true
  enable_deletion_protection = true
  access_logs {
    bucket  = aws_s3_bucket.alb_logs.id
    enabled = true
  }
  depends_on = [aws_s3_bucket_policy.alb_logs]
}

resource "aws_lb_target_group" "web" {
  #checkov:skip=CKV_AWS_378:TLS terminé à l'ALB ; cibles en sous-réseaux privés filtrés par groupe de sécurité (chiffrement de bout en bout : backlog SEC-11)
  name        = "${var.name}-web"
  port        = 3000
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = var.vpc_id
  health_check {
    path    = "/"
    matcher = "200"
  }
}

resource "aws_lb_target_group" "auth" {
  #checkov:skip=CKV_AWS_378:TLS terminé à l'ALB ; cibles en sous-réseaux privés filtrés par groupe de sécurité (chiffrement de bout en bout : backlog SEC-11)
  name        = "${var.name}-auth"
  port        = 8080
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = var.vpc_id
  health_check {
    path    = "/realms/avocat-expert/.well-known/openid-configuration"
    matcher = "200"
  }
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.this.arn
  port              = 80
  protocol          = "HTTP"
  default_action {
    type = "redirect"
    redirect {
      port        = "443"
      protocol    = "HTTPS"
      status_code = "HTTP_301"
    }
  }
}

resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.this.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = var.certificate_arn
  default_action {
    type = "fixed-response"
    fixed_response {
      content_type = "text/plain"
      message_body = "Introuvable"
      status_code  = "404"
    }
  }
}

resource "aws_lb_listener_rule" "web" {
  listener_arn = aws_lb_listener.https.arn
  priority     = 10
  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.web.arn
  }
  condition {
    host_header {
      values = [var.app_host]
    }
  }
}

resource "aws_lb_listener_rule" "auth" {
  listener_arn = aws_lb_listener.https.arn
  priority     = 20
  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.auth.arn
  }
  condition {
    host_header {
      values = [var.auth_host]
    }
  }
}

resource "aws_wafv2_web_acl" "this" {
  name  = var.name
  scope = "REGIONAL"
  default_action {
    allow {}
  }
  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = var.name
    sampled_requests_enabled   = false
  }

  rule {
    name     = "AWSManagedRulesCommonRuleSet"
    priority = 10
    override_action {
      none {}
    }
    statement {
      managed_rule_group_statement {
        vendor_name = "AWS"
        name        = "AWSManagedRulesCommonRuleSet"
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "AWSManagedRulesCommonRuleSet"
      sampled_requests_enabled   = false
    }
  }

  rule {
    name     = "AWSManagedRulesKnownBadInputsRuleSet"
    priority = 20
    override_action {
      none {}
    }
    statement {
      managed_rule_group_statement {
        vendor_name = "AWS"
        name        = "AWSManagedRulesKnownBadInputsRuleSet"
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "AWSManagedRulesKnownBadInputsRuleSet"
      sampled_requests_enabled   = false
    }
  }

  rule {
    name     = "AWSManagedRulesAmazonIpReputationList"
    priority = 30
    override_action {
      none {}
    }
    statement {
      managed_rule_group_statement {
        vendor_name = "AWS"
        name        = "AWSManagedRulesAmazonIpReputationList"
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "AWSManagedRulesAmazonIpReputationList"
      sampled_requests_enabled   = false
    }
  }

  rule {
    name     = "limitation-debit-par-ip"
    priority = 40
    action {
      block {}
    }
    statement {
      rate_based_statement {
        limit              = var.rate_limit_per_5min
        aggregate_key_type = "IP"
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "limitation-debit-par-ip"
      sampled_requests_enabled   = false
    }
  }
}

resource "aws_wafv2_web_acl_association" "this" {
  resource_arn = aws_lb.this.arn
  web_acl_arn  = aws_wafv2_web_acl.this.arn
}

resource "aws_cloudwatch_log_group" "waf" {
  name              = "aws-waf-logs-${var.name}"
  retention_in_days = 365
  kms_key_id        = var.logs_kms_key_arn
}

# Journaux WAF sans en-têtes d'authentification ni cookies.
resource "aws_wafv2_web_acl_logging_configuration" "this" {
  resource_arn            = aws_wafv2_web_acl.this.arn
  log_destination_configs = [aws_cloudwatch_log_group.waf.arn]
  redacted_fields {
    single_header {
      name = "authorization"
    }
  }
  redacted_fields {
    single_header {
      name = "cookie"
    }
  }
}

output "alb_security_group_id" {
  value = aws_security_group.alb.id
}

output "web_target_group_arn" {
  value = aws_lb_target_group.web.arn
}

output "auth_target_group_arn" {
  value = aws_lb_target_group.auth.arn
}

output "alb_dns_name" {
  value = aws_lb.this.dns_name
}
