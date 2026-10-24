variable "project" {
  type    = string
  default = "avocat-expert"
}

variable "environment" {
  type    = string
  default = "staging"
}

variable "image_tag" {
  type        = string
  description = "Étiquette immuable des images à déployer (empreinte du commit)"
}

variable "certificate_arn" {
  type        = string
  description = "Certificat ACM eu-west-3 pour app_host et auth_host"
}

variable "app_host" {
  type = string
}

variable "auth_host" {
  type = string
}

variable "otel_exporter_endpoint" {
  type    = string
  default = ""
}

variable "monthly_budget_usd" {
  type    = number
  default = 500
}

variable "budget_alert_emails" {
  type = list(string)
}
