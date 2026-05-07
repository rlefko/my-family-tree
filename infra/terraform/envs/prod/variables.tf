variable "region" {
  type    = string
  default = "us-east-1"
}

variable "api_image" {
  type    = string
  default = "ghcr.io/rlefkowitz/my-family-tree-backend:latest"
}

variable "certificate_arn" {
  type        = string
  description = "ACM certificate ARN for the prod ALB HTTPS listener"
  default     = ""
}

variable "cors_allowed_origins" {
  type    = list(string)
  default = []
}
