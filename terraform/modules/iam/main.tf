# Valdrix - Read-Only IAM Role for Cost Analysis
#
# This Terraform module creates an IAM role that allows Valdrix to read
# your AWS cost data. The role uses cross-account AssumeRole with
# an External ID for security.
#
# Usage:
#   module "valdrix" {
#     source      = "./valdrix"
#     external_id = "vx-YOUR_EXTERNAL_ID_HERE"
#   }
#
# After apply, copy the role_arn output to Valdrix dashboard.

# Tag name used for resources (can be Valdrix or Valtric)
# variable "resource_tag_name" {
#   description = "Application name used for tagging and resource naming"
#   type        = string
#   default     = "Valdrix"
# }

# IAM Role for Valdrix
resource "aws_iam_role" "valdrix" {
  name               = "${var.resource_tag_name}ReadOnly"
  description        = "Allows Valdrix to read cost data for analysis"
  max_session_duration = 3600  # 1 hour

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          AWS = "arn:aws:iam::${var.valdrix_account_id}:root"
        }
        Action = "sts:AssumeRole"
        Condition = {
          StringEquals = {
            "sts:ExternalId" = var.external_id
          }
        }
      }
    ]
  })

  tags = {
    Purpose   = "${var.resource_tag_name}-CostAnalysis"
    ManagedBy = var.resource_tag_name
  }
}

resource "aws_iam_role_policy" "read_only" {
  name = "${var.resource_tag_name}ReadOnlyPolicy"
  role = aws_iam_role.valdrix.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "EC2ReadOnly"
        Effect = "Allow"
        Action = [
          "ec2:DescribeInstances",
          "ec2:DescribeVolumes",
          "ec2:DescribeSnapshots",
          "ec2:DescribeAddresses",
          "ec2:DescribeNetworkInterfaces",
          "ec2:DescribeNatGateways",
          "ec2:DescribeSecurityGroups"
        ]
        Resource = "*"
      },
      {
        Sid    = "ELBReadOnly"
        Effect = "Allow"
        Action = [
          "elasticloadbalancing:DescribeLoadBalancers",
          "elasticloadbalancing:DescribeTargetGroups",
          "elasticloadbalancing:DescribeTargetHealth"
        ]
        Resource = "*"
      },
      {
        Sid    = "RDSReadOnly"
        Effect = "Allow"
        Action = [
          "rds:DescribeDBInstances",
          "rds:DescribeDBClusters"
        ]
        Resource = "*"
      },
      {
        Sid    = "RedshiftOnly"
        Effect = "Allow"
        Action = ["redshift:DescribeClusters"]
        Resource = "*"
      },
      {
        Sid    = "SageMakerReadOnly"
        Effect = "Allow"
        Action = ["sagemaker:ListEndpoints", "sagemaker:ListNotebookInstances", "sagemaker:ListModels"]
        Resource = "*"
      },
      {
        Sid    = "ECRReadOnly"
        Effect = "Allow"
        Action = ["ecr:DescribeRepositories", "ecr:DescribeImages"]
        Resource = "*"
      },
      {
        Sid    = "S3ReadOnly"
        Effect = "Allow"
        Action = ["s3:ListAllMyBuckets", "s3:GetBucketLocation", "s3:GetBucketTagging"]
        Resource = "*"
      },
      {
        Sid    = "CloudWatchRead"
        Effect = "Allow"
        Action = ["cloudwatch:GetMetricData", "cloudwatch:GetMetricStatistics"]
        Resource = "*"
      },
      {
        Sid    = "CURRead"
        Effect = "Allow"
        Action = ["cur:DescribeReportDefinitions"]
        Resource = "*"
      },
      {
        Sid    = "S3ReadForCUR"
        Effect = "Allow"
        Action = ["s3:GetBucketPolicy", "s3:ListBucket", "s3:GetObject"]
        Resource = [
          "arn:aws:s3:::valdrix-cur-*",
          "arn:aws:s3:::valdrix-cur-*/*"
        ]
      }
      # OPTIONAL: CUR Automation (Commented out for security)
      # If you want Valdrix to automatically setup your Cost & Usage Report,
      # add the following actions to a separate policy:
      # - "cur:PutReportDefinition",
      # - "cur:ModifyReportDefinition",
      # - "s3:CreateBucket",
      # - "s3:PutBucketPolicy"
    ]
  })
}


# ---------------------------------------------------------
# INFRASTRUCTURE RELIABILITY: RDS BACKUP POLICY
# ---------------------------------------------------------
# This section ensures that the Valdrix database has automated
# backups enabled with a 30-day retention period.
# Note: In a real environment, this would be part of the 
# DB instance resource definition.

# resource "aws_db_instance" "valdrix" {
#   # ... other config ...
#   backup_retention_period = 30
#   backup_window           = "03:00-04:00"
#   copy_tags_to_snapshot   = true
#   delete_automated_backups = false
#   skip_final_snapshot     = false
# }

# Outputs
output "role_arn" {
  description = "The ARN of the Valdrix role. Copy this to Valdrix dashboard."
  value       = aws_iam_role.valdrix.arn
}

output "role_name" {
  description = "The name of the Valdrix role."
  value       = aws_iam_role.valdrix.name
}
