variable "name_prefix" {
  type = string
}

variable "names" {
  type    = list(string)
  default = []
}

variable "tags" {
  type    = map(string)
  default = {}
}
