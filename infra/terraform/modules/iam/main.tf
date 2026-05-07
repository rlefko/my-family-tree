data "aws_iam_policy_document" "task_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "task_execution" {
  name               = "${var.name_prefix}-task-execution"
  assume_role_policy = data.aws_iam_policy_document.task_assume.json
  tags               = var.tags
}

resource "aws_iam_role_policy_attachment" "task_execution_aws" {
  role       = aws_iam_role.task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

data "aws_iam_policy_document" "secrets_read" {
  count = length(var.secret_arns) > 0 ? 1 : 0
  statement {
    actions   = ["secretsmanager:GetSecretValue"]
    resources = var.secret_arns
  }
}

resource "aws_iam_role_policy" "task_execution_secrets" {
  count  = length(var.secret_arns) > 0 ? 1 : 0
  name   = "${var.name_prefix}-task-execution-secrets"
  role   = aws_iam_role.task_execution.id
  policy = data.aws_iam_policy_document.secrets_read[0].json
}

resource "aws_iam_role" "task" {
  name               = "${var.name_prefix}-task"
  assume_role_policy = data.aws_iam_policy_document.task_assume.json
  tags               = var.tags
}

data "aws_iam_policy_document" "s3_rw" {
  count = var.s3_bucket_arn == "" ? 0 : 1
  statement {
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject", "s3:ListBucket"]
    resources = [var.s3_bucket_arn, "${var.s3_bucket_arn}/*"]
  }
}

resource "aws_iam_role_policy" "task_s3" {
  count  = var.s3_bucket_arn == "" ? 0 : 1
  name   = "${var.name_prefix}-task-s3"
  role   = aws_iam_role.task.id
  policy = data.aws_iam_policy_document.s3_rw[0].json
}
