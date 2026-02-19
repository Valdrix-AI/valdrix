import boto3
import sys
import time
from botocore.exceptions import ClientError

def delete_cloudfront(distribution_id):
    client = boto3.client('cloudfront')
    
    print(f"Waiting for distribution {distribution_id} to be fully disabled...")
    
    # Poll for status
    while True:
        try:
            response = client.get_distribution_config(Id=distribution_id)
            config = response['DistributionConfig']
            etag = response['ETag']
            
            # Check if execution failed or needs refresh
            dist_response = client.get_distribution(Id=distribution_id)
            status = dist_response['Distribution']['Status']
            
            if config['Enabled']:
                print(f"Distribution is still enabled. Disabling...")
                config['Enabled'] = False
                client.update_distribution(Id=distribution_id, IfMatch=etag, DistributionConfig=config)
                time.sleep(5)
                continue
                
            if status != 'Deployed':
                print(f"Distribution status is '{status}'. Waiting for 'Deployed'...")
                time.sleep(15)
                continue
                
            print(f"Distribution is disabled and deployed. Attempting deletion...")
            client.delete_distribution(Id=distribution_id, IfMatch=etag)
            print(f"Successfully deleted {distribution_id}.")
            return True
            
        except ClientError as e:
            if e.response['Error']['Code'] == 'DistributionNotDisabled':
                 print(f"AWS reports distribution not disabled yet. Retrying...")
                 time.sleep(10)
                 continue
            elif e.response['Error']['Code'] == 'InvalidIfMatchVersion':
                 print("ETag mismatch, retrying...")
                 continue
            else:
                print(f"ClientError: {e}")
                return False
        except Exception as e:
            print(f"Error: {e}")
            return False
            
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 delete_cloudfront.py <distribution_id>")
        sys.exit(1)
        
    delete_cloudfront(sys.argv[1])
