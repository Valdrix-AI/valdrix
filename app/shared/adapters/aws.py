from app.shared.adapters.aws_multitenant import MultiTenantAWSAdapter

# Restore generic AWSAdapter for backward compatibility with existing tests
AWSAdapter = MultiTenantAWSAdapter
