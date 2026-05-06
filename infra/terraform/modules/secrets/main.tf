resource "aws_secretsmanager_secret" "this" {
  for_each    = toset(var.names)
  name        = "${var.name_prefix}/${each.key}"
  description = "${var.name_prefix} ${each.key}"
  tags        = var.tags
}
