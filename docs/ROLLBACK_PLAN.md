# Valdrics Rollback & Disaster Recovery Plan

Procedures for reverting changes in case of deployment failure.

## 1. Database Migrations (Alembic)
If a migration fails or causes data corruption:

1. **Step Back**: `alembic downgrade -1`
2. **Specific Version**: `alembic downgrade [VERSION_ID]`
3. **Verification**: After rollback, verify schema via `\d [table_name]` in psql.

## 2. Infrastructure (Terraform/CloudFormation)
1. **Terraform**: `terraform apply` with the previous version from Git history.
2. **CloudFormation**: Use the "Rollback" feature in the AWS Console for the specific stack.

## 3. Application Deployment
1. **Koyeb/Vercel**: Re-deploy the previous successful commit hash from the main branch.
2. **Health Check**: Monitor `/health` immediately after rollback.

## 4. Emergency Soft-Kill
To stop all background processing (e.g., recursive job loop):
1. **Env Flag**: Set `ENABLE_SCHEDULER=false`.
2. **Restart**: Force restart all containers.
