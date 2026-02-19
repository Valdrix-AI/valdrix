import boto3
import sys
import time

def disable_cloudfront(distribution_id):
    client = boto3.client('cloudfront')
    
    try:
        # Get current config
        response = client.get_distribution_config(Id=distribution_id)
        etag = response['ETag']
        config = response['DistributionConfig']
        
        if not config['Enabled']:
            print(f"Distribution {distribution_id} is already disabled.")
            return True
            
        print(f"Disabling distribution {distribution_id}...")
        config['Enabled'] = False
        
        client.update_distribution(
            Id=distribution_id,
            IfMatch=etag,
            DistributionConfig=config
        )
        print(f"Successfully disabled {distribution_id}.")
        return True
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return False

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 disable_cloudfront.py <distribution_id>")
        sys.exit(1)
        
    disable_cloudfront(sys.argv[1])
