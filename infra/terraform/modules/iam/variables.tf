variable "name_prefix" {
  type = string
}

variable "s3_bucket_arn" {
  type    = string
  default = ""
}

variable "secret_arns" {
  type    = list(string)
  default = []
}

variable "tags" {
  type    = map(string)
  default = {}
}
