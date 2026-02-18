# Multi-Cloud Zombie Detection Reference (2026)

> Comprehensive API reference for implementing zombie resource detection across AWS, Azure, and GCP.
> **Code Location:** `app/modules/optimization/domain/` and `app/modules/optimization/adapters/`

---

## 📊 Zombie Resource Categories

| Category | Description | Typical Waste |
|----------|-------------|---------------|
| **Storage** | Unattached disks, old snapshots, unused buckets | 5-15% of storage spend |
| **Compute** | Idle VMs, stopped instances, unused containers | 20-40% of compute spend |
| **Network** | Unused IPs, orphan LBs, empty VPCs | $50-200/month per resource |
| **Database** | Idle databases, oversized instances | 15-30% of DB spend |
| **Security** | Stale credentials, unused SGs | Security risk |
| **AI/ML** | Idle endpoints, orphan models | $100-1000/month |

---

## 🟠 AWS Zombie Detection Reference

### EC2 Compute

#### Idle EC2 Instances
```python
import boto3
from datetime import datetime, timedelta

def find_idle_ec2_instances(ec2_client, cw_client, cpu_threshold=5.0, days=7):
    """
    Find EC2 instances with avg CPU < threshold over specified days.
    
    Returns:
        List of {instance_id, avg_cpu, instance_type, monthly_cost}
    """
    instances = ec2_client.describe_instances(
        Filters=[{'Name': 'instance-state-name', 'Values': ['running']}]
    )
    
    idle_instances = []
    end_time = datetime.utcnow()
    start_time = end_time - timedelta(days=days)
    
    for reservation in instances['Reservations']:
        for instance in reservation['Instances']:
            instance_id = instance['InstanceId']
            
            # Get CPU metrics
            metrics = cw_client.get_metric_statistics(
                Namespace='AWS/EC2',
                MetricName='CPUUtilization',
                Dimensions=[{'Name': 'InstanceId', 'Value': instance_id}],
                StartTime=start_time,
                EndTime=end_time,
                Period=86400,  # 1 day
                Statistics=['Average']
            )
            
            if metrics['Datapoints']:
                avg_cpu = sum(d['Average'] for d in metrics['Datapoints']) / len(metrics['Datapoints'])
                if avg_cpu < cpu_threshold:
                    idle_instances.append({
                        'resource_id': instance_id,
                        'resource_type': 'EC2 Instance',
                        'instance_type': instance['InstanceType'],
                        'avg_cpu_percent': round(avg_cpu, 2),
                        'launch_time': instance['LaunchTime'].isoformat(),
                        'recommendation': 'Stop or terminate if not needed',
                        'action': 'stop_instance'
                    })
    
    return idle_instances
```

#### Stopped EC2 Instances (Still Paying for EBS!)
```python
def find_stopped_ec2_instances(ec2_client, days_threshold=14):
    """
    Find EC2 instances stopped for more than threshold days.
    Note: Still incurring EBS storage costs!
    """
    instances = ec2_client.describe_instances(
        Filters=[{'Name': 'instance-state-name', 'Values': ['stopped']}]
    )
    
    stopped_zombies = []
    cutoff = datetime.utcnow() - timedelta(days=days_threshold)
    
    for reservation in instances['Reservations']:
        for instance in reservation['Instances']:
            # Check state transition time
            state_reason = instance.get('StateTransitionReason', '')
            # Format: "User initiated (2026-01-01 00:00:00 GMT)"
            
            stopped_zombies.append({
                'resource_id': instance['InstanceId'],
                'resource_type': 'Stopped EC2',
                'instance_type': instance['InstanceType'],
                'recommendation': 'Terminate or create AMI and terminate',
                'action': 'terminate_instance'
            })
    
    return stopped_zombies
```

### Load Balancers

```python
def find_orphan_load_balancers(elb_client, cw_client):
    """
    Find ALBs/NLBs with no healthy targets or zero connections.
    """
    load_balancers = elb_client.describe_load_balancers()
    orphan_lbs = []
    
    for lb in load_balancers['LoadBalancers']:
        lb_arn = lb['LoadBalancerArn']
        lb_name = lb['LoadBalancerName']
        
        # Check target groups
        target_groups = elb_client.describe_target_groups(
            LoadBalancerArn=lb_arn
        )
        
        has_healthy_targets = False
        for tg in target_groups['TargetGroups']:
            health = elb_client.describe_target_health(
                TargetGroupArn=tg['TargetGroupArn']
            )
            healthy = [t for t in health['TargetHealthDescriptions'] 
                      if t['TargetHealth']['State'] == 'healthy']
            if healthy:
                has_healthy_targets = True
                break
        
        if not has_healthy_targets:
            orphan_lbs.append({
                'resource_id': lb_name,
                'resource_type': 'Load Balancer',
                'lb_type': lb['Type'],
                'monthly_cost': 16.43,  # Base ALB cost
                'recommendation': 'Delete if no longer needed',
                'action': 'delete_load_balancer'
            })
    
    return orphan_lbs
```

### RDS Databases

```python
def find_idle_rds_databases(rds_client, cw_client, connection_threshold=1, days=7):
    """
    Find RDS instances with < threshold connections over specified days.
    """
    databases = rds_client.describe_db_instances()
    idle_dbs = []
    
    end_time = datetime.utcnow()
    start_time = end_time - timedelta(days=days)
    
    for db in databases['DBInstances']:
        db_id = db['DBInstanceIdentifier']
        
        metrics = cw_client.get_metric_statistics(
            Namespace='AWS/RDS',
            MetricName='DatabaseConnections',
            Dimensions=[{'Name': 'DBInstanceIdentifier', 'Value': db_id}],
            StartTime=start_time,
            EndTime=end_time,
            Period=86400,
            Statistics=['Average']
        )
        
        if metrics['Datapoints']:
            avg_connections = sum(d['Average'] for d in metrics['Datapoints']) / len(metrics['Datapoints'])
            if avg_connections < connection_threshold:
                idle_dbs.append({
                    'resource_id': db_id,
                    'resource_type': 'RDS Database',
                    'db_class': db['DBInstanceClass'],
                    'engine': db['Engine'],
                    'avg_connections': round(avg_connections, 2),
                    'recommendation': 'Stop or delete if not needed',
                    'action': 'stop_rds_instance'
                })
    
    return idle_dbs
```

### NAT Gateways

```python
def find_underused_nat_gateways(ec2_client, cw_client, gb_threshold=1.0, days=30):
    """
    Find NAT Gateways with < threshold GB data in specified days.
    NAT Gateway costs $32/month + data processing.
    """
    nat_gateways = ec2_client.describe_nat_gateways(
        Filters=[{'Name': 'state', 'Values': ['available']}]
    )
    
    underused = []
    end_time = datetime.utcnow()
    start_time = end_time - timedelta(days=days)
    
    for nat in nat_gateways['NatGateways']:
        nat_id = nat['NatGatewayId']
        
        metrics = cw_client.get_metric_statistics(
            Namespace='AWS/NATGateway',
            MetricName='BytesOutToDestination',
            Dimensions=[{'Name': 'NatGatewayId', 'Value': nat_id}],
            StartTime=start_time,
            EndTime=end_time,
            Period=86400 * days,  # Entire period
            Statistics=['Sum']
        )
        
        total_bytes = sum(d['Sum'] for d in metrics.get('Datapoints', []))
        total_gb = total_bytes / (1024**3)
        
        if total_gb < gb_threshold:
            underused.append({
                'resource_id': nat_id,
                'resource_type': 'NAT Gateway',
                'vpc_id': nat['VpcId'],
                'data_processed_gb': round(total_gb, 2),
                'monthly_cost': 32.40,  # Base cost alone
                'recommendation': 'Consider NAT instances or VPC endpoints',
                'action': 'delete_nat_gateway'
            })
    
    return underused
```

### IAM Security

```python
def find_stale_iam_credentials(iam_client, days_threshold=90):
    """
    Find IAM users with credentials not used in specified days.
    Security risk! These should be disabled or deleted.
    """
    # Generate and retrieve credential report
    iam_client.generate_credential_report()
    
    import time
    time.sleep(5)  # Wait for report generation
    
    report = iam_client.get_credential_report()
    content = report['Content'].decode('utf-8')
    
    import csv
    from io import StringIO
    
    reader = csv.DictReader(StringIO(content))
    stale_creds = []
    cutoff = datetime.utcnow() - timedelta(days=days_threshold)
    
    for row in reader:
        user = row['user']
        
        # Check password last used
        password_last_used = row.get('password_last_used', 'N/A')
        
        # Check access keys
        access_key_1_active = row.get('access_key_1_active') == 'true'
        access_key_1_last_used = row.get('access_key_1_last_used_date', 'N/A')
        
        if access_key_1_active and access_key_1_last_used not in ['N/A', 'no_information']:
            try:
                last_used = datetime.fromisoformat(access_key_1_last_used.replace('Z', '+00:00'))
                if last_used.replace(tzinfo=None) < cutoff:
                    stale_creds.append({
                        'resource_id': user,
                        'resource_type': 'IAM Access Key',
                        'days_since_use': (datetime.utcnow() - last_used.replace(tzinfo=None)).days,
                        'recommendation': 'Disable or delete stale credentials',
                        'action': 'deactivate_access_key',
                        'severity': 'security'
                    })
            except:
                pass
    
    return stale_creds
```

---

## 🔵 Azure Zombie Detection Reference

### Authentication Setup
```python
from azure.identity import ClientSecretCredential
from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.network import NetworkManagementClient
from azure.mgmt.monitor import MonitorManagementClient

def get_azure_clients(tenant_id, client_id, client_secret, subscription_id):
    credential = ClientSecretCredential(
        tenant_id=tenant_id,
        client_id=client_id,
        client_secret=client_secret
    )
    
    return {
        'compute': ComputeManagementClient(credential, subscription_id),
        'network': NetworkManagementClient(credential, subscription_id),
        'monitor': MonitorManagementClient(credential, subscription_id)
    }
```

### Unattached Managed Disks
```python
def find_unattached_azure_disks(compute_client):
    """
    Find Azure Managed Disks not attached to any VM.
    """
    disks = compute_client.disks.list()
    unattached = []
    
    for disk in disks:
        if disk.disk_state == 'Unattached':
            unattached.append({
                'resource_id': disk.name,
                'resource_type': 'Managed Disk',
                'size_gb': disk.disk_size_gb,
                'sku': disk.sku.name,
                'location': disk.location,
                'monthly_cost': disk.disk_size_gb * 0.05,  # Approximate
                'recommendation': 'Delete if not needed',
                'action': 'delete_disk'
            })
    
    return unattached
```

### Stopped/Deallocated VMs
```python
def find_stopped_azure_vms(compute_client):
    """
    Find VMs that have been deallocated (not running but taking space).
    """
    vms = compute_client.virtual_machines.list_all()
    stopped = []
    
    for vm in vms:
        # Get instance view for power state
        instance_view = compute_client.virtual_machines.instance_view(
            resource_group_name=vm.id.split('/')[4],
            vm_name=vm.name
        )
        
        for status in instance_view.statuses:
            if 'PowerState/deallocated' in status.code:
                stopped.append({
                    'resource_id': vm.name,
                    'resource_type': 'Azure VM',
                    'vm_size': vm.hardware_profile.vm_size,
                    'location': vm.location,
                    'recommendation': 'Delete or resize if not needed',
                    'action': 'delete_vm'
                })
    
    return stopped
```

### Unused Public IPs
```python
def find_unused_azure_public_ips(network_client):
    """
    Find Public IPs not associated with any resource.
    """
    public_ips = network_client.public_ip_addresses.list_all()
    unused = []
    
    for ip in public_ips:
        if ip.ip_configuration is None:
            unused.append({
                'resource_id': ip.name,
                'resource_type': 'Public IP',
                'ip_address': ip.ip_address,
                'sku': ip.sku.name,
                'monthly_cost': 3.65,  # Standard static IP
                'recommendation': 'Release if not needed',
                'action': 'release_public_ip'
            })
    
    return unused
```

---

## 🟢 GCP Zombie Detection Reference

### Authentication Setup
```python
from google.cloud import compute_v1
from google.cloud import monitoring_v3
from google.oauth2 import service_account

def get_gcp_clients(service_account_json, project_id):
    credentials = service_account.Credentials.from_service_account_file(
        service_account_json,
        scopes=['https://www.googleapis.com/auth/cloud-platform']
    )
    
    return {
        'instances': compute_v1.InstancesClient(credentials=credentials),
        'disks': compute_v1.DisksClient(credentials=credentials),
        'addresses': compute_v1.AddressesClient(credentials=credentials),
        'monitoring': monitoring_v3.MetricServiceClient(credentials=credentials),
        'project_id': project_id
    }
```

### Unattached Persistent Disks
```python
def find_unattached_gcp_disks(disk_client, project_id):
    """
    Find GCP Persistent Disks not attached to any instance.
    """
    unattached = []
    
    # List all disks across all zones
    request = compute_v1.AggregatedListDisksRequest(project=project_id)
    disks = disk_client.aggregated_list(request=request)
    
    for zone, response in disks:
        if response.disks:
            for disk in response.disks:
                if not disk.users:  # Not attached to any instance
                    unattached.append({
                        'resource_id': disk.name,
                        'resource_type': 'Persistent Disk',
                        'size_gb': disk.size_gb,
                        'disk_type': disk.type_.split('/')[-1],
                        'zone': zone.split('/')[-1],
                        'monthly_cost': int(disk.size_gb) * 0.04,  # pd-standard
                        'recommendation': 'Delete if not needed',
                        'action': 'delete_disk'
                    })
    
    return unattached
```

### Unused External IPs
```python
def find_unused_gcp_addresses(address_client, project_id):
    """
    Find GCP external IPs not in use.
    """
    unused = []
    
    request = compute_v1.AggregatedListAddressesRequest(project=project_id)
    addresses = address_client.aggregated_list(request=request)
    
    for region, response in addresses:
        if response.addresses:
            for addr in response.addresses:
                if addr.status == 'RESERVED':  # Not IN_USE
                    unused.append({
                        'resource_id': addr.name,
                        'resource_type': 'External IP',
                        'ip_address': addr.address,
                        'region': region.split('/')[-1],
                        'monthly_cost': 7.30,  # Unused static IP
                        'recommendation': 'Release if not needed',
                        'action': 'release_address'
                    })
    
    return unused
```

### Terminated Instances (Old)
```python
def find_old_terminated_gcp_instances(instance_client, project_id, days=30):
    """
    Find instances that have been terminated for a long time.
    These clutter the console and may have associated resources.
    """
    from datetime import datetime, timedelta
    
    old_terminated = []
    cutoff = datetime.utcnow() - timedelta(days=days)
    
    request = compute_v1.AggregatedListInstancesRequest(project=project_id)
    instances = instance_client.aggregated_list(request=request)
    
    for zone, response in instances:
        if response.instances:
            for instance in response.instances:
                if instance.status == 'TERMINATED':
                    old_terminated.append({
                        'resource_id': instance.name,
                        'resource_type': 'Terminated Instance',
                        'machine_type': instance.machine_type.split('/')[-1],
                        'zone': zone.split('/')[-1],
                        'recommendation': 'Delete terminated instance',
                        'action': 'delete_instance'
                    })
    
    return old_terminated
```

---

## 📋 Required Permissions Summary

### AWS
```json
{
  "ec2:Describe*",
  "elasticloadbalancing:Describe*",
  "rds:Describe*",
  "lambda:List*",
  "iam:GenerateCredentialReport",
  "iam:GetCredentialReport",
  "cloudwatch:GetMetricStatistics"
}
```

### Azure
```
Microsoft.Compute/*/read
Microsoft.Network/*/read
Microsoft.Sql/*/read
Microsoft.Monitor/metrics/read
```

### GCP
```
compute.instances.list
compute.disks.list
compute.addresses.list
compute.snapshots.list
monitoring.timeSeries.list
```

---

## 🔧 Dashboard Integration

Each zombie type should have:

1. **Card Display** - Resource ID, type, age, estimated cost
2. **Action Buttons** - Delete, Stop, Create Backup, Ignore
3. **Bulk Actions** - Select multiple and batch remediate
4. **Filters** - By type, cost, age, region
5. **Approval Workflow** - Request → Review → Execute

---

*Last Updated: January 2026*
