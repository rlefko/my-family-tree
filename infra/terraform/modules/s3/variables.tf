variable "bucket_name" {
  type = string
}

variable "enable_versioning" {
  type    = bool
  default = true
}

variable "cors_allowed_origins" {
  type    = list(string)
  default = []
}

variable "tags" {
  type    = map(string)
  default = {}
}
