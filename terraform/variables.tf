
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

variable "enable_active_enforcement" {
  description = "Attach tag-scoped active remediation IAM permissions."
  type        = bool
  default     = false
}

variable "active_enforcement_resource_tag_key" {
  description = "Resource tag key required for active enforcement actions."
  type        = string
  default     = "ValdricsManaged"
}

variable "active_enforcement_resource_tag_value" {
  description = "Resource tag value required for active enforcement actions."
  type        = string
  default     = "true"
}
