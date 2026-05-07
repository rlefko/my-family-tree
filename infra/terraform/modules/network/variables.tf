variable "name_prefix" {
  type = string
}

variable "vpc_cidr" {
  type    = string
  default = "10.20.0.0/16"
}

variable "az_count" {
  type    = number
  default = 2
}

variable "single_nat" {
  type        = bool
  default     = true
  description = "Use a single NAT gateway (dev) or one per AZ (prod)"
}

variable "tags" {
  type    = map(string)
  default = {}
}
