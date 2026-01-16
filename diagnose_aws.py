import boto3
import sys
import argparse
from botocore.exceptions import ClientError

def diagnose_aws(role_arn, external_id):
    """
    Diagnose AWS AssumeRole issues.
    """
    print("=== Valdrix AWS Diagnostic Tool ===")
    
    # 1. Check current identity
    sts = boto3.client('sts')
    try:
        identity = sts.get_caller_identity()
        print(f"[*] Current IAM Identity: {identity['Arn']}")
        print(f"[*] Account ID: {identity['Account']}")
        user_account = identity['Account']
    except ClientError as e:
        print(f"[!] Error: Could not get caller identity. Check your AWS_ACCESS_KEY_ID/SECRET.")
        print(f"    Details: {str(e)}")
        return

    # 2. Check if trying to assume role in same account
    target_account = role_arn.split(':')[4]
    print(f"[*] Target Role Account: {target_account}")
    
    if user_account == target_account:
        print("[!] Note: You are assuming a role in the SAME account. This is valid but unusual for production cross-account flows.")

    # 3. Attempt AssumeRole
    print(f"[*] Attempting AssumeRole...")
    print(f"    ARN: {role_arn}")
    print(f"    ExternalId: {external_id}")
    
    try:
        response = sts.assume_role(
            RoleArn=role_arn,
            RoleSessionName="ValdrixDiagnostic",
            ExternalId=external_id,
            DurationSeconds=900
        )
        print("[SUCCESS] Successfully assumed the role!")
        print(f"[SUCCESS] Credentials expire at: {response['Credentials']['Expiration']}")
        
    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', 'Unknown')
        print(f"\n[FAILURE] AssumeRole failed with error: {error_code}")
        print(f"Details: {str(e)}")
        
        print("\n--- Troubleshooting Advice ---")
        if error_code == 'AccessDenied':
            print("1. [YOUR LOCAL USER] Missing AssumeRole permission.")
            print(f"   Go to IAM Console -> Users -> {identity['Arn'].split('/')[-1]}")
            print("   Add an inline policy to allow 'sts:AssumeRole' on the specific Role ARN.")
            
            print("\n2. [REMOTE ROLE] Trust Policy mismatch.")
            print(f"   Go to IAM Console -> Roles -> (The Role being assumed)")
            print("   Ensure the 'Trust Relationships' tab allows YOUR account root or user.")
            print(f"   Principal should include: \"AWS\": \"arn:aws:iam::{user_account}:root\"")
            
            print("\n3. [REMOTE ROLE] External ID mismatch.")
            print(f"   Ensure the Role Trust Policy Condition 'sts:ExternalId' EXACTLY matches:")
            print(f"   '{external_id}'")
            
        elif error_code == 'MalformedPolicyDocument':
            print("The Role ARN or External ID provided might be invalid.")
        else:
            print("Please check the AWS CloudTrail logs in the target account for more details.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Diagnose AWS AssumeRole issues for Valdrix.")
    parser.add_argument("role_arn", help="Full ARN of the IAM Role to assume")
    parser.add_argument("external_id", help="External ID required by the role's trust policy")
    
    args = parser.parse_args()
    
    diagnose_aws(args.role_arn, args.external_id)
