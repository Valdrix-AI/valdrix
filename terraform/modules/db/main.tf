
data "aws_vpc" "selected" {
  id = var.vpc_id
}

resource "aws_db_subnet_group" "main" {
  name       = "valdrix-db-subnet-group-${var.environment}"
  subnet_ids = var.private_subnet_ids

  tags = {
    Name = "Valdrix DB Subnet Group"
  }
}

resource "aws_security_group" "rds" {
  name        = "valdrix-rds-sg-${var.environment}"
  description = "Allow inbound traffic from EKS"
  vpc_id      = var.vpc_id

  ingress {
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [var.eks_worker_sg_id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = [data.aws_vpc.selected.cidr_block]
  }

  tags = {
    Name = "valdrix-rds-sg-${var.environment}"
  }
}

resource "aws_db_instance" "main" {
  allocated_storage      = 20
  storage_type           = "gp3"
  engine                 = "postgres"
  engine_version         = "16.3"
  instance_class         = var.db_instance_class
  db_name                = var.db_name
  username               = var.db_username
  password               = var.db_password
  parameter_group_name   = "default.postgres16"
  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  skip_final_snapshot    = var.skip_final_snapshot
  
  backup_retention_period = 30
  backup_window           = "03:00-04:00"
  copy_tags_to_snapshot   = true

  tags = {
    Name        = "valdrix-db-${var.environment}"
    Environment = var.environment
  }
}
