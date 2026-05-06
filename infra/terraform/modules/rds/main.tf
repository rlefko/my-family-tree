resource "aws_db_subnet_group" "this" {
  name       = "${var.name_prefix}-db-subnets"
  subnet_ids = var.subnet_ids
  tags       = var.tags
}

resource "aws_security_group" "db" {
  name        = "${var.name_prefix}-db-sg"
  description = "Postgres + pgvector"
  vpc_id      = var.vpc_id
  tags        = var.tags
}

resource "aws_security_group_rule" "db_in" {
  type              = "ingress"
  from_port         = 5432
  to_port           = 5432
  protocol          = "tcp"
  cidr_blocks       = var.allowed_cidr_blocks
  security_group_id = aws_security_group.db.id
}

resource "aws_db_parameter_group" "this" {
  name        = "${var.name_prefix}-pg17-pgvector"
  family      = "postgres17"
  description = "Enable pgvector + pg_trgm shared_preload_libraries"

  parameter {
    name         = "shared_preload_libraries"
    value        = "pg_trgm,vector"
    apply_method = "pending-reboot"
  }
}

resource "aws_db_instance" "this" {
  identifier                  = "${var.name_prefix}-postgres"
  engine                      = "postgres"
  engine_version              = "17.2"
  instance_class              = var.instance_class
  allocated_storage           = var.allocated_storage
  storage_type                = "gp3"
  storage_encrypted           = true
  db_name                     = var.db_name
  username                    = var.master_username
  manage_master_user_password = true
  parameter_group_name        = aws_db_parameter_group.this.name
  db_subnet_group_name        = aws_db_subnet_group.this.name
  vpc_security_group_ids      = [aws_security_group.db.id]
  multi_az                    = var.multi_az
  publicly_accessible         = false
  skip_final_snapshot         = !var.deletion_protection
  deletion_protection         = var.deletion_protection
  backup_retention_period     = var.backup_retention_period
  tags                        = var.tags
}
