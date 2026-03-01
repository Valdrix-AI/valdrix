# Emergency Cloud Disconnect Runbook

**Version:** 1.0  
**Status:** Active  
**Author:** Valdrics Platform Team

## Overview
This runbook provides instructions for immediate disconnection of a cloud provider account from Valdrics in case of a security incident or at the customer's request.

## Target Audience
- Valdrics Security Engineers
- Customer Cloud Administrators

## Procedure

### 1. In-App Disconnect
1. Login to Valdrics Admin/Dashboard.
2. Navigate to **Connections**.
3. Locate the connection to be removed.
4. Click **Delete/Disconnect**.
5. Confirm deletion. This will:
   - Mark the connection as `deleted` in the Valdrics DB.
   - Stop all ongoing scans and health checks.
   - Revoke access to the connection in the application layer.

### 2. AWS Side Revocation (Manual)
If the Valdrics app is unavailable or the situation is urgent:
1. Login to the **AWS Management Console** of the connected account.
2. Navigate to **IAM > Roles**.
3. Search for the role assumed by Valdrics (e.g., `Valdrix-AI-Role` or `Valdrix-Role`).
4. **Delete the role** OR **Remove the Trust Relationship** of the role.
   - Removing the trust relationship is less destructive and prevents Valdrics from assuming the role without deleting the role itself.
5. Search for the **IAM Policy** associated with the role and delete it.

### 3. Verification
1. Attempt to run a scan in the Valdrics dashboard; it should fail with an `AccessDenied` or `ResourceNotFound` error.
2. Check the Audit Log in AWS for `AssumeRole` failures from the Valdrics Principal ARN.

---

# Data Retention & Purge Policy

