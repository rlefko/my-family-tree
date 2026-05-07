terraform {
  required_version = ">= 1.9.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.70"
    }
  }
}

provider "aws" {
  region = var.region
}

locals {
  name_prefix = "my-family-tree-dev"
  tags = {
    Project = "my-family-tree"
    Env     = "dev"
  }
}

module "network" {
  source      = "../../modules/network"
  name_prefix = local.name_prefix
  single_nat  = true
  tags        = local.tags
}

module "s3" {
  source               = "../../modules/s3"
  bucket_name          = "${local.name_prefix}-documents"
  cors_allowed_origins = var.cors_allowed_origins
  tags                 = local.tags
}

module "secrets" {
  source      = "../../modules/secrets"
  name_prefix = local.name_prefix
  names = [
    "llm/openai_api_key",
    "llm/anthropic_api_key",
    "app/secret_key",
  ]
  tags = local.tags
}

module "iam" {
  source        = "../../modules/iam"
  name_prefix   = local.name_prefix
  s3_bucket_arn = module.s3.bucket_arn
  secret_arns   = values(module.secrets.secret_arns)
  tags          = local.tags
}

module "rds" {
  source              = "../../modules/rds"
  name_prefix         = local.name_prefix
  vpc_id              = module.network.vpc_id
  subnet_ids          = module.network.private_subnet_ids
  allowed_cidr_blocks = ["10.20.0.0/16"]
  instance_class      = "db.t4g.micro"
  multi_az            = false
  deletion_protection = false
  tags                = local.tags
}

module "alb" {
  source            = "../../modules/alb"
  name_prefix       = local.name_prefix
  vpc_id            = module.network.vpc_id
  public_subnet_ids = module.network.public_subnet_ids
  certificate_arn   = ""
  tags              = local.tags
}

module "ecs" {
  source                  = "../../modules/ecs"
  name_prefix             = local.name_prefix
  vpc_id                  = module.network.vpc_id
  private_subnet_ids      = module.network.private_subnet_ids
  alb_security_group_id   = module.alb.security_group_id
  task_execution_role_arn = module.iam.task_execution_role_arn
  task_role_arn           = module.iam.task_role_arn
  log_retention_days      = 7

  services = {
    api = {
      image            = var.api_image
      cpu              = 256
      memory           = 512
      command          = ["uvicorn", "my_family_tree.api.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
      ports            = [8000]
      env              = { APP_ENV = "production", LOG_LEVEL = "info" }
      secrets          = {}
      desired_count    = 1
      target_group_arn = module.alb.target_group_arn_api
    }
    worker = {
      image         = var.api_image
      cpu           = 256
      memory        = 512
      command       = ["arq", "my_family_tree.workers.arq_app.WorkerSettings"]
      ports         = []
      env           = { APP_ENV = "production", LOG_LEVEL = "info" }
      secrets       = {}
      desired_count = 1
    }
    mcp = {
      image            = var.api_image
      cpu              = 256
      memory           = 512
      command          = ["python", "-m", "my_family_tree.cli", "mcp", "--transport", "http", "--host", "0.0.0.0", "--port", "8765"]
      ports            = [8765]
      env              = { APP_ENV = "production", LOG_LEVEL = "info" }
      secrets          = {}
      desired_count    = 1
      target_group_arn = module.alb.target_group_arn_mcp
    }
  }
  tags = local.tags
}

output "alb_dns_name" {
  value = module.alb.alb_dns_name
}

output "documents_bucket" {
  value = module.s3.bucket_name
}

output "rds_endpoint" {
  value = module.rds.endpoint
}
