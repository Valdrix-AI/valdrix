locals {
  resolved_runtime_secret_name = length(trimspace(var.runtime_secret_name)) > 0 ? trimspace(var.runtime_secret_name) : "/valdrics/${var.environment}/app-runtime"
}

resource "aws_kms_key" "runtime_secrets" {
  description             = "Valdrics runtime secret envelope key (${var.environment})"
  enable_key_rotation     = true
  deletion_window_in_days = 30

  tags = {
    Name        = "valdrics-runtime-secrets-kms-${var.environment}"
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

resource "aws_kms_alias" "runtime_secrets" {
  name          = "alias/valdrics-runtime-secrets-${var.environment}"
  target_key_id = aws_kms_key.runtime_secrets.key_id
}

resource "aws_secretsmanager_secret" "runtime" {
  name                    = local.resolved_runtime_secret_name
  description             = "Valdrics runtime secrets for ${var.environment}"
  kms_key_id              = aws_kms_key.runtime_secrets.arn
  recovery_window_in_days = 30

  lifecycle {
    precondition {
      condition     = !contains(["prod", "production"], lower(var.environment)) || var.enable_secret_rotation
      error_message = "enable_secret_rotation must be true for prod/production environments."
    }
  }

  tags = {
    Name        = "valdrics-runtime-secret-${var.environment}"
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}

resource "aws_secretsmanager_secret_version" "runtime_initial" {
  count         = length(trimspace(var.runtime_secret_initial_json)) > 0 ? 1 : 0
  secret_id     = aws_secretsmanager_secret.runtime.id
  secret_string = var.runtime_secret_initial_json
}

resource "aws_secretsmanager_secret_rotation" "runtime" {
  count               = var.enable_secret_rotation ? 1 : 0
  secret_id           = aws_secretsmanager_secret.runtime.id
  rotation_lambda_arn = var.rotation_lambda_arn

  rotation_rules {
    automatically_after_days = 90
  }
}
