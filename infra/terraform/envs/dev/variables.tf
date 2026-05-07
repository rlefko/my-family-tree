variable "region" {
  type    = string
  default = "us-east-1"
}

variable "api_image" {
  type        = string
  description = "Container image for the api/worker/mcp services. Wire to your ECR repo."
  default     = "ghcr.io/rlefkowitz/my-family-tree-backend:latest"
}

variable "cors_allowed_origins" {
  type    = list(string)
  default = []
}
