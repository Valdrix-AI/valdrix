
variable "external_id" {
  type = string
}

variable "valdrix_account_id" {
  type = string
}

variable "resource_tag_name" {
  type    = string
  default = "Valdrix"
}

variable "enable_active_enforcement" {
  description = "Enable tag-scoped active remediation IAM actions."
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
