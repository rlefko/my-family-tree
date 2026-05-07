variable "name_prefix" {
  type = string
}

variable "vpc_id" {
  type = string
}

variable "private_subnet_ids" {
  type = list(string)
}

variable "alb_security_group_id" {
  type = string
}

variable "task_execution_role_arn" {
  type = string
}

variable "task_role_arn" {
  type = string
}

variable "log_retention_days" {
  type    = number
  default = 14
}

variable "services" {
  type = map(object({
    image            = string
    cpu              = number
    memory           = number
    command          = list(string)
    ports            = list(number)
    env              = map(string)
    secrets          = map(string)
    desired_count    = number
    target_group_arn = optional(string)
  }))
}

variable "tags" {
  type    = map(string)
  default = {}
}
