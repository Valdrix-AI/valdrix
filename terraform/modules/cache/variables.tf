
variable "vpc_id" {
  type = string
}

variable "private_subnet_ids" {
  type = list(string)
}

variable "eks_worker_sg_id" {
  type = string
}

variable "environment" {
  type = string
}
