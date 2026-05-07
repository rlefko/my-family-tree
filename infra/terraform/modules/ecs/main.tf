resource "aws_ecs_cluster" "this" {
  name = "${var.name_prefix}-cluster"
  setting {
    name  = "containerInsights"
    value = "enabled"
  }
  tags = var.tags
}

resource "aws_security_group" "tasks" {
  name        = "${var.name_prefix}-tasks-sg"
  description = "ECS tasks egress + ALB ingress"
  vpc_id      = var.vpc_id
  tags        = var.tags

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group_rule" "tasks_from_alb" {
  type                     = "ingress"
  from_port                = 0
  to_port                  = 65535
  protocol                 = "tcp"
  source_security_group_id = var.alb_security_group_id
  security_group_id        = aws_security_group.tasks.id
}

resource "aws_cloudwatch_log_group" "this" {
  for_each          = var.services
  name              = "/ecs/${var.name_prefix}/${each.key}"
  retention_in_days = var.log_retention_days
  tags              = var.tags
}

resource "aws_ecs_task_definition" "this" {
  for_each                 = var.services
  family                   = "${var.name_prefix}-${each.key}"
  cpu                      = each.value.cpu
  memory                   = each.value.memory
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  execution_role_arn       = var.task_execution_role_arn
  task_role_arn            = var.task_role_arn

  container_definitions = jsonencode([
    {
      name      = each.key
      image     = each.value.image
      essential = true
      command   = each.value.command
      portMappings = [
        for p in each.value.ports : {
          containerPort = p
          protocol      = "tcp"
        }
      ]
      environment = [
        for k, v in each.value.env : { name = k, value = v }
      ]
      secrets = [
        for k, v in each.value.secrets : { name = k, valueFrom = v }
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.this[each.key].name
          "awslogs-region"        = data.aws_region.current.name
          "awslogs-stream-prefix" = each.key
        }
      }
    }
  ])
}

resource "aws_ecs_service" "this" {
  for_each        = var.services
  name            = "${var.name_prefix}-${each.key}"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.this[each.key].arn
  desired_count   = each.value.desired_count
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [aws_security_group.tasks.id]
    assign_public_ip = false
  }

  dynamic "load_balancer" {
    for_each = each.value.target_group_arn == null ? [] : [each.value.target_group_arn]
    content {
      target_group_arn = load_balancer.value
      container_name   = each.key
      container_port   = each.value.ports[0]
    }
  }

  deployment_minimum_healthy_percent = 50
  deployment_maximum_percent         = 200
  enable_execute_command             = true
}

data "aws_region" "current" {}
