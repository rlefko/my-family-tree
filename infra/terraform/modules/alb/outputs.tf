output "alb_arn" {
  value = aws_lb.this.arn
}

output "alb_dns_name" {
  value = aws_lb.this.dns_name
}

output "security_group_id" {
  value = aws_security_group.alb.id
}

output "target_group_arn_api" {
  value = aws_lb_target_group.api.arn
}

output "target_group_arn_mcp" {
  value = aws_lb_target_group.mcp.arn
}
