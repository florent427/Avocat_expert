variable "name" {
  type = string
}

variable "kms_key_arn" {
  type = string
}

variable "max_receive_count" {
  type    = number
  default = 5
}

resource "aws_sqs_queue" "dead_letter" {
  name                      = "${var.name}-dlq"
  kms_master_key_id         = var.kms_key_arn
  message_retention_seconds = 1209600
}

resource "aws_sqs_queue" "this" {
  name                       = var.name
  kms_master_key_id          = var.kms_key_arn
  visibility_timeout_seconds = 300
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dead_letter.arn
    maxReceiveCount     = var.max_receive_count
  })
}

output "queue_arn" {
  value = aws_sqs_queue.this.arn
}
