
variable "vpc_id" {
  type = string
}

variable "private_subnet_ids" {
  type = list(string)
}

variable "environment" {
  type = string
}

variable "cluster_name" {
  type    = string
  default = "valdrics"
}

variable "node_instance_types" {
  type    = list(string)
  default = ["t3.medium"]
}
