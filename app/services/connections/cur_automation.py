import json
import aioboto3
import structlog
from botocore.exceptions import ClientError
from app.models.aws_connection import AWSConnection

logger = structlog.get_logger()

class IAMCURManager:
    """
    Automates the setup of AWS Cost and Usage Reports (CUR).
    Uses the assumed IAM role to create buckets and define reports.
    """

    def __init__(self, connection: AWSConnection):
        self.connection = connection
        self.session = aioboto3.Session()

    async def setup_cur_automation(self) -> dict:
        """
        Main entry point for 'Zero-Touch' CUR setup.
        """
        creds = await self._get_credentials()
        account_id = self.connection.aws_account_id
        region = self.connection.region
        bucket_name = f"valdrix-cur-{account_id}-{region}"
        report_name = f"valdrix-cur-v2-{account_id}"

        try:
            # 1. Create S3 Bucket
            await self._create_s3_bucket(creds, bucket_name, region)

            # 2. Attach Bucket Policy for CUR Delivery
            await self._attach_bucket_policy(creds, bucket_name, account_id)

            # 3. Define CUR 2.0 Report
            await self._put_report_definition(creds, bucket_name, report_name, region)

            logger.info("cur_automation_setup_success", 
                        account_id=account_id, 
                        bucket=bucket_name, 
                        report=report_name)
            
            return {
                "status": "success",
                "bucket_name": bucket_name,
                "report_name": report_name
            }

        except Exception as e:
            logger.error("cur_automation_setup_failed", 
                         account_id=account_id, 
                         error=str(e), 
                         exc_info=True)
            raise

    async def _get_credentials(self) -> dict:
        from app.services.adapters.aws_multitenant import MultiTenantAWSAdapter
        adapter = MultiTenantAWSAdapter(self.connection)
        return await adapter.get_credentials()

    async def _create_s3_bucket(self, creds: dict, bucket_name: str, region: str):
        async with self.session.client(
            "s3",
            region_name=region,
            aws_access_key_id=creds["AccessKeyId"],
            aws_secret_access_key=creds["SecretAccessKey"],
            aws_session_token=creds["SessionToken"],
        ) as s3:
            try:
                # Check if bucket exists
                await s3.head_bucket(Bucket=bucket_name)
                logger.debug("cur_bucket_already_exists", bucket=bucket_name)
            except ClientError as e:
                if e.response["Error"]["Code"] == "404":
                    # Create bucket
                    # Note: LocationConstraint is needed for regions other than us-east-1
                    config = {"LocationConstraint": region} if region != "us-east-1" else None
                    if config:
                        await s3.create_bucket(Bucket=bucket_name, CreateBucketConfiguration=config)
                    else:
                        await s3.create_bucket(Bucket=bucket_name)
                    logger.info("cur_bucket_created", bucket=bucket_name)
                else:
                    raise

    async def _attach_bucket_policy(self, creds: dict, bucket_name: str, account_id: str):
        policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Sid": "AllowCURDelivery",
                    "Effect": "Allow",
                    "Principal": {
                        "Service": "billingreports.amazonaws.com"
                    },
                    "Action": [
                        "s3:GetBucketAcl",
                        "s3:GetBucketPolicy"
                    ],
                    "Resource": f"arn:aws:s3:::{bucket_name}",
                    "Condition": {
                        "StringEquals": {
                            "aws:SourceAccount": account_id,
                            "aws:SourceArn": f"arn:aws:cur:us-east-1:{account_id}:definition/*"
                        }
                    }
                },
                {
                    "Sid": "AllowCURPutObject",
                    "Effect": "Allow",
                    "Principal": {
                        "Service": "billingreports.amazonaws.com"
                    },
                    "Action": "s3:PutObject",
                    "Resource": f"arn:aws:s3:::{bucket_name}/*",
                    "Condition": {
                        "StringEquals": {
                            "aws:SourceAccount": account_id,
                            "aws:SourceArn": f"arn:aws:cur:us-east-1:{account_id}:definition/*"
                        }
                    }
                }
            ]
        }

        async with self.session.client(
            "s3",
            aws_access_key_id=creds["AccessKeyId"],
            aws_secret_access_key=creds["SecretAccessKey"],
            aws_session_token=creds["SessionToken"],
        ) as s3:
            await s3.put_bucket_policy(Bucket=bucket_name, Policy=json.dumps(policy))
            logger.info("cur_bucket_policy_attached", bucket=bucket_name)

    async def _put_report_definition(self, creds: dict, bucket_name: str, report_name: str, region: str):
        # CUR 2.0 (Data Exports) is preferred, but PutReportDefinition is standard for CUR 1.0/Legacy.
        # Most automation still uses 'cur' client.
        async with self.session.client(
            "cur",
            region_name="us-east-1", # CUR client must be in us-east-1
            aws_access_key_id=creds["AccessKeyId"],
            aws_secret_access_key=creds["SecretAccessKey"],
            aws_session_token=creds["SessionToken"],
        ) as cur:
            report_definition = {
                "ReportName": report_name,
                "TimeUnit": "HOURLY",
                "Format": "Parquet",
                "Compression": "GZIP",
                "AdditionalSchemaElements": ["RESOURCES"],
                "S3Bucket": bucket_name,
                "S3Prefix": "cur",
                "S3Region": region,
                "AdditionalArtifacts": ["ATHENA"],
                "RefreshClosedReports": True,
                "ReportVersioning": "OVERWRITE_EXISTING"
            }

            try:
                await cur.put_report_definition(ReportDefinition=report_definition)
                logger.info("cur_report_defined", report=report_name)
            except ClientError as e:
                if e.response["Error"]["Code"] == "DuplicateReportNameException":
                    logger.warning("cur_report_already_exists", report=report_name)
                else:
                    raise
