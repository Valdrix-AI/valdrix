"""
Centralized Pricing Defaults
Consolidates resource costs across providers and regions.
"""

# Standardized hourly rates (USD)
DEFAULT_RATES = {
    "aws": {
        "volume": {
            "gp2": 0.10 / 720,  # $0.10/GB-month
            "gp3": 0.08 / 720,  # $0.08/GB-month
        },
        "ip": 0.005,  # $0.005/hour for unused EIP
        "instance": {
            "t3.micro": 0.0104,
            "t3.medium": 0.0416,
            "m5.large": 0.096,
        },
        "nat_gateway": 0.045,  # $0.045 per hour
        "elb": 0.0225,  # ~$16/month
        "rds": {
            "db.t3.micro": 0.017,
            "db.t3.small": 0.034,
            "db.t3.medium": 0.068,
            "db.t3.large": 0.136,
        },
        "redshift": 0.25,  # $0.25/hour per node
        "sagemaker": 0.15,  # $0.15/hour per endpoint instance
        "ecr": 0.10 / 720,  # $0.10/GB-month
        # OpenSearch on-demand baseline rates (hourly)
        "opensearch": {
            "t3.small.search": 0.036,
            "t3.medium.search": 0.072,
            "m6g.large.search": 0.138,
            "r6g.large.search": 0.192,
            "default": 0.036,
        },
        # Dedicated master nodes for OpenSearch
        "opensearch_master": {
            "t3.small.search": 0.036,
            "m6g.large.search": 0.138,
            "default": 0.036,
        },
    },
    "gcp": {
        "ip": 0.01,  # ~$7.20/month
        "instance": {
            "gpu": 1500.0 / 730,  # ~$1500/month
            "n1-standard": 100.0 / 730,
            "micro": 5.0 / 730,
            "default": 50.0 / 730,
        },
        "disk": 0.04 / 730,  # $0.04/GB-month (standard)
        "image": 0.05 / 730,
    },
    "azure": {
        "ip": 0.004,  # ~$2.90/month
        "instance": {
            "gpu": 1200.0 / 730,
            "standard_d": 150.0 / 730,
            "standard_b": 20.0 / 730,
            "default": 100.0 / 730,
        },
        "disk": 0.05 / 730,
        "image": 0.03 / 730,
        # Provisioned throughput unit approximation for Azure OpenAI.
        # Note: exact billing varies by model/region and should be overridden by live catalogs.
        "azure_openai_ptu": {
            "ptu": 8.22,  # ~$6000/month
            "default": 8.22,
        },
    },
}

# Regional multipliers (Based on Industry Benchmarks)
REGION_MULTIPLIERS = {
    # US Regions (Baseline)
    "us-east-1": 1.0,
    "us-east-2": 1.0,
    "us-central1": 1.0,
    "eastus": 1.0,
    "westus": 1.05,
    "us-west-1": 1.08,
    "us-west-2": 1.0,
    # EU Regions
    "eu-west-1": 1.10,
    "eu-west-2": 1.15,
    "eu-west-3": 1.12,
    "eu-central-1": 1.12,
    "westeurope": 1.10,
    "northeurope": 1.10,
    # Asia Pacific
    "ap-southeast-1": 1.20,
    "ap-southeast-2": 1.22,
    "ap-northeast-1": 1.25,
    "ap-south-1": 1.15,
    # LATAM & Africa
    "sa-east-1": 1.35,
    "af-south-1": 1.25,
}
