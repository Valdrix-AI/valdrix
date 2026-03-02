# Valdrics - Read-Only IAM Role for Cost Analysis
#
# This Terraform module creates an IAM role that allows Valdrics to read
# your AWS cost data. The role uses cross-account AssumeRole with
# an External ID for security.
#
# Usage:
#   module "valdrics" {
#     source      = "./valdrics"
#     external_id = "vx-YOUR_EXTERNAL_ID_HERE"
#   }
#
# After apply, copy the role_arn output to Valdrics dashboard.

# Tag name used for resources (can be Valdrics or Valtric)
# variable "resource_tag_name" {
#   description = "Application name used for tagging and resource naming"
#   type        = string
#   default     = "Valdrics"
# }

# IAM Role for Valdrics
resource "aws_iam_role" "valdrics" {
  name                 = "${var.resource_tag_name}ReadOnly"
  description          = "Allows Valdrics to read cost data for analysis"
  max_session_duration = 3600 # 1 hour

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          AWS = "arn:aws:iam::${var.valdrics_account_id}:root"
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
  role = aws_iam_role.valdrics.id

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
        Sid      = "RedshiftOnly"
        Effect   = "Allow"
        Action   = ["redshift:DescribeClusters"]
        Resource = "*"
      },
      {
        Sid      = "SageMakerReadOnly"
        Effect   = "Allow"
        Action   = ["sagemaker:ListEndpoints", "sagemaker:ListNotebookInstances", "sagemaker:ListModels"]
        Resource = "*"
      },
      {
        Sid      = "ECRReadOnly"
        Effect   = "Allow"
        Action   = ["ecr:DescribeRepositories", "ecr:DescribeImages"]
        Resource = "*"
      },
      {
        Sid      = "S3ReadOnly"
        Effect   = "Allow"
        Action   = ["s3:ListAllMyBuckets", "s3:GetBucketLocation", "s3:GetBucketTagging"]
        Resource = "*"
      },
      {
        Sid      = "CloudWatchRead"
        Effect   = "Allow"
        Action   = ["cloudwatch:GetMetricData", "cloudwatch:GetMetricStatistics"]
        Resource = "*"
      },
      {
        Sid      = "CURRead"
        Effect   = "Allow"
        Action   = ["cur:DescribeReportDefinitions"]
        Resource = "*"
      },
      {
        Sid    = "S3ReadForCUR"
        Effect = "Allow"
        Action = ["s3:GetBucketPolicy", "s3:ListBucket", "s3:GetObject"]
        Resource = [
          "arn:aws:s3:::valdrics-cur-*",
          "arn:aws:s3:::valdrics-cur-*/*"
        ]
      }
    ]
  })
}

resource "aws_iam_role_policy" "active_enforcement" {
  count = var.enable_active_enforcement ? 1 : 0

  name = "${var.resource_tag_name}ActiveEnforcementPolicy"
  role = aws_iam_role.valdrics.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "Ec2LifecycleControlsTagged"
        Effect = "Allow"
        Action = [
          "ec2:StopInstances",
          "ec2:StartInstances",
          "ec2:RebootInstances",
          "ec2:TerminateInstances",
          "ec2:ModifyInstanceAttribute"
        ]
        Resource = "arn:aws:ec2:*:*:instance/*"
        Condition = {
          StringEquals = {
            "aws:ResourceTag/${var.active_enforcement_resource_tag_key}" = var.active_enforcement_resource_tag_value
          }
        }
      },
      {
        Sid    = "RdsLifecycleControlsTagged"
        Effect = "Allow"
        Action = [
          "rds:StartDBInstance",
          "rds:StopDBInstance",
          "rds:RebootDBInstance",
          "rds:ModifyDBInstance"
        ]
        Resource = "arn:aws:rds:*:*:db:*"
        Condition = {
          StringEquals = {
            "aws:ResourceTag/${var.active_enforcement_resource_tag_key}" = var.active_enforcement_resource_tag_value
          }
        }
      },
      {
        Sid    = "AsgScaleControlsTagged"
        Effect = "Allow"
        Action = [
          "autoscaling:SetDesiredCapacity",
          "autoscaling:UpdateAutoScalingGroup"
        ]
        Resource = "arn:aws:autoscaling:*:*:autoScalingGroup:*:autoScalingGroupName/*"
        Condition = {
          StringEquals = {
            "autoscaling:ResourceTag/${var.active_enforcement_resource_tag_key}" = var.active_enforcement_resource_tag_value
          }
        }
      },
      {
        Sid    = "LambdaConcurrencyControlsTagged"
        Effect = "Allow"
        Action = [
          "lambda:PutFunctionConcurrency",
          "lambda:DeleteFunctionConcurrency",
          "lambda:UpdateFunctionConfiguration"
        ]
        Resource = "arn:aws:lambda:*:*:function:*"
        Condition = {
          StringEquals = {
            "aws:ResourceTag/${var.active_enforcement_resource_tag_key}" = var.active_enforcement_resource_tag_value
          }
        }
      },
      {
        Sid    = "EcsServiceScaleControlsTagged"
        Effect = "Allow"
        Action = [
          "ecs:UpdateService"
        ]
        Resource = "arn:aws:ecs:*:*:service/*/*"
        Condition = {
          StringEquals = {
            "aws:ResourceTag/${var.active_enforcement_resource_tag_key}" = var.active_enforcement_resource_tag_value
          }
        }
      }
    ]
  })
}


# ---------------------------------------------------------
# INFRASTRUCTURE RELIABILITY: RDS BACKUP POLICY
# ---------------------------------------------------------
# This section ensures that the Valdrics database has automated
# backups enabled with a 30-day retention period.
# Note: In a real environment, this would be part of the 
# DB instance resource definition.

# resource "aws_db_instance" "valdrics" {
#   # ... other config ...
#   backup_retention_period = 30
#   backup_window           = "03:00-04:00"
#   copy_tags_to_snapshot   = true
#   delete_automated_backups = false
#   skip_final_snapshot     = false
# }

# Outputs
output "role_arn" {
  description = "The ARN of the Valdrics role. Copy this to Valdrics dashboard."
  value       = aws_iam_role.valdrics.arn
}

output "role_name" {
  description = "The name of the Valdrics role."
  value       = aws_iam_role.valdrics.name
}

output "active_enforcement_enabled" {
  description = "Whether the active enforcement policy is attached."
  value       = var.enable_active_enforcement
}
