
data "aws_vpc" "selected" {
  id = var.vpc_id
}

resource "aws_elasticache_subnet_group" "main" {
  name       = "valdrics-cache-subnet-group-${var.environment}"
  subnet_ids = var.private_subnet_ids
}

resource "aws_security_group" "redis" {
  name        = "valdrics-redis-sg-${var.environment}"
  vpc_id      = var.vpc_id

  ingress {
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [var.eks_worker_sg_id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = [data.aws_vpc.selected.cidr_block]
  }
}

resource "aws_elasticache_replication_group" "main" {
  replication_group_id = "valdrics-redis-${var.environment}"
  description          = "Valdrics Redis cache (${var.environment})"
  engine               = "redis"
  engine_version       = "7.0"
  node_type            = "cache.t3.micro"
  num_cache_clusters   = 1
  parameter_group_name = "default.redis7"
  port                 = 6379
  subnet_group_name    = aws_elasticache_subnet_group.main.name
  security_group_ids   = [aws_security_group.redis.id]
  at_rest_encryption_enabled = true
  transit_encryption_enabled = true
  automatic_failover_enabled = false
  multi_az_enabled           = false

  tags = {
    Name        = "valdrics-redis-${var.environment}"
    Environment = var.environment
  }
}
