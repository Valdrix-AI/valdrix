# Changelog

All notable changes to Valdrics will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Helm chart for Kubernetes deployment (`helm/valdrics/`)
- Grafana dashboards for API and FinOps metrics
- Pre-commit hooks for code quality
- Prometheus alerting rules
- Docker Compose observability stack
- Architecture documentation with Mermaid diagrams

## [1.0.0] - 2026-02-03

### Added
- **Multi-Cloud Support**: AWS, Azure, and GCP adapters
- **11 Zombie Detection Plugins**: EC2, EBS, S3, RDS, NAT, ELB, SageMaker, Redshift, ECR, EIPs, Lambda
- **Zero-API-Cost Architecture**: Uses AWS CUR, GCP BigQuery, Azure Cost Exports
- **Multi-LLM Analysis**: OpenAI, Anthropic, Google Gemini, Groq support
- **GreenOps Integration**: Carbon footprint tracking with CodeCarbon
- **Slack Alerts**: Real-time notifications with leaderboards
- **Human-in-the-Loop Remediation**: Approval workflow with audit trail
- **SvelteKit Dashboard**: Dark mode, responsive design
- **Multi-Tenant Architecture**: Supabase Auth with Row-Level Security
- **ActiveOps Engine**: Autonomous remediation with configurable policies

### Security
- Zero-trust architecture with STS AssumeRole
- Read-only IAM permissions by default
- Encrypted secrets with Fernet
- CSRF protection on all endpoints
- Rate limiting per tenant

### Infrastructure
- FastAPI backend with async SQLAlchemy
- PostgreSQL with Neon serverless
- Redis caching layer
- OpenTelemetry observability
- GitHub Actions CI/CD with security scanning
- SBOM generation with CycloneDX

## [0.1.0] - 2026-01-15

### Added
- Initial project structure
- Basic AWS Cost Explorer integration
- Simple zombie detection logic
- Prototype dashboard

---

## Release Notes Format

### Categories
- **Added** for new features
- **Changed** for changes in existing functionality
- **Deprecated** for soon-to-be removed features
- **Removed** for now removed features
- **Fixed** for any bug fixes
- **Security** for vulnerability fixes
