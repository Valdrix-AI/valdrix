from app.shared.adapters.aws_multitenant import MultiTenantAWSAdapter
from app.shared.adapters.aws_cur import AWSCURAdapter

# Restore generic AWSAdapter for backward compatibility with existing tests
AWSAdapter = MultiTenantAWSAdapter
