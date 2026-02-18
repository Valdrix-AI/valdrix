# EKS Private Networking & Connectivity

## Security Architecture
The EKS cluster is deployed with `endpoint_public_access = false` and `endpoint_private_access = true` for maximum security. This ensures the Kubernetes API server is not exposed to the public internet.

## Access Requirements
To interact with the cluster via `kubectl`, you must be connected to the VPC via one of the following methods:

1. **VPN Gateway / Client VPN**:
   - Establish a VPN connection to the VPC.
   - Ensure your VPN security group allows traffic to the EKS cluster security group on port 443.

2. **Bastion Host (Jump Box)**:
   - SSH into a bastion host located in a public subnet.
   - Use SSH forwarding or run `kubectl` commands directly from the bastion.

3. **Direct Connect**:
   - For enterprise environments, use AWS Direct Connect for a dedicated network link.

## Security Warning
> [!WARNING]
> Do NOT enable public endpoint access without strictly limiting CIDR blocks. Private endpoints are the recommended configuration for production-grade security.
