
variable "vpc_id" {
  description = "VPC ID where RDS should be deployed"
  type        = string
}

variable "private_subnet_ids" {
  description = "Private subnets for RDS"
  type        = list(string)
}

variable "eks_worker_sg_id" {
  description = "Security Group ID of EKS worker nodes for DB access"
  type        = string
}

variable "environment" {
  description = "Environment name"
  type        = string
}

variable "db_instance_class" {
  type    = string
  default = "db.t3.medium"
}

variable "db_name" {
  type    = string
  default = "valdrix"
}

variable "db_password" {
  description = "Master password for the RDS instance. Use Secrets Manager or a secure TF variable store."
  type        = string
  sensitive   = true
}

variable "db_username" {
  description = "Username for the RDS instance."
  type        = string
  default     = "valdrix_admin"
}

variable "skip_final_snapshot" {
  description = "Whether to skip final snapshot on DB deletion. Set false for production."
  type        = bool
  default     = false
}
