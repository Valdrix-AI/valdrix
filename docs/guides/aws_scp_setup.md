# AWS SCP Deployment Guide

## Overview
Service Control Policies (SCPs) provide central control over the maximum available permissions for all accounts in an organization. This guide explains how to use SCPs to protect Valdrix integrations.

## Recommended SCPs

### 1. Protect Valdrix IAM Role
This SCP prevents any user (including the root user) from deleting or modifying the Valdrix cross-account role.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "DenyDeleteValdrixRole",
      "Effect": "Deny",
      "Action": [
        "iam:DeleteRole",
        "iam:DeleteRolePolicy",
        "iam:DetachRolePolicy",
        "iam:UpdateRole",
        "iam:UpdateRoleDescription"
      ],
      "Resource": [
        "arn:aws:iam::*:role/CloudSentinel-AI-Role"
      ]
    }
  ]
}
```

### 2. Restrict Remediation Regions
Limit the regions where Valdrix (or any entity) can perform destructive actions.

## Deployment Steps
1. Login to the AWS Organizations management account.
2. Enable Service Control Policies in the Settings.
3. Create a new policy with the JSON above.
4. Attach the policy to the target OUs or accounts.

