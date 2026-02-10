
variable "aws_region" {
  default = "us-east-1"
}

variable "environment" {
  default = "prod"
}

variable "external_id" {
  description = "External ID for Valdrix cross-account access"
  type        = string
}

variable "valdrix_account_id" {
  description = "Valdrix's central account ID"
  type        = string
}
