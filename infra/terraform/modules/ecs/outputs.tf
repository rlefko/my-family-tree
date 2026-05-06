output "cluster_arn" {
  value = aws_ecs_cluster.this.arn
}

output "service_arns" {
  value = { for k, s in aws_ecs_service.this : k => s.id }
}
