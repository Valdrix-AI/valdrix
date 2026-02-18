import boto3
import sys

def disassociate_waf(distribution_id):
    client = boto3.client('cloudfront')
    
    # 1. Get current config and ETag
    try:
        response = client.get_distribution_config(Id=distribution_id)
        etag = response['ETag']
        config = response['DistributionConfig']
        
        # 2. Check if already disassociated
        if not config.get('WebACLId'):
            print(f"Distribution {distribution_id} already has no Web ACL.")
            return True
            
        print(f"Disassociating Web ACL {config['WebACLId']} from {distribution_id}...")
        
        # 3. Modify config
        config['WebACLId'] = ''
        
        # 4. Update distribution
        client.update_distribution(
            Id=distribution_id,
            IfMatch=etag,
            DistributionConfig=config
        )
        print(f"Successfully started disassociation for {distribution_id}.")
        return True
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return False

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 disassociate_waf.py <distribution_id>")
        sys.exit(1)
        
    disassociate_waf(sys.argv[1])
