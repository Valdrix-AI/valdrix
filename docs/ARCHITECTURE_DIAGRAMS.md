# Valdrix Architecture

This document provides a visual overview of the Valdrix system architecture.

## System Overview

```mermaid
graph TB
    subgraph "Client Layer"
        UI[SvelteKit Dashboard]
        SLACK[Slack Integration]
    end

    subgraph "API Gateway"
        API[FastAPI + Uvicorn]
        AUTH[Supabase Auth + RLS]
    end

    subgraph "Core Services"
        SCAN[Scan Orchestrator]
        ZOMBIE[Zombie Detection Engine]
        LLM[Multi-LLM Analyzer]
        REMED[Remediation Engine]
        ACTIVE[ActiveOps Autopilot]
    end

    subgraph "Detection Plugins"
        EC2[EC2 Plugin]
        EBS[EBS Plugin]
        RDS[RDS Plugin]
        S3[S3 Plugin]
        MORE[+8 More Plugins]
    end

    subgraph "Cloud Adapters"
        AWS[AWS Adapter<br/>CUR + Resource Explorer]
        GCP[GCP Adapter<br/>BigQuery Export]
        AZURE[Azure Adapter<br/>Cost Export]
    end

    subgraph "Data Layer"
        PG[(PostgreSQL<br/>Neon)]
        REDIS[(Redis<br/>Cache)]
    end

    subgraph "Observability"
        OTEL[OpenTelemetry]
        PROM[Prometheus]
        GRAF[Grafana]
    end

    UI --> API
    SLACK --> API
    API --> AUTH
    AUTH --> SCAN
    SCAN --> ZOMBIE
    ZOMBIE --> EC2 & EBS & RDS & S3 & MORE
    EC2 & EBS & RDS & S3 --> AWS
    ZOMBIE --> LLM
    LLM --> REMED
    REMED --> ACTIVE
    ACTIVE --> AWS & GCP & AZURE
    API --> PG
    API --> REDIS
    API --> OTEL
    OTEL --> PROM
    PROM --> GRAF
```

## Data Flow

```mermaid
sequenceDiagram
    participant User
    participant Dashboard
    participant API
    participant ScanEngine
    participant Plugins
    participant Cloud
    participant LLM
    participant Slack

    User->>Dashboard: Connect AWS Account
    Dashboard->>API: POST /connections
    API->>Cloud: Validate IAM Role

    Note over API,Cloud: Daily Scan Trigger

    API->>ScanEngine: Start Scan
    ScanEngine->>Plugins: Run Detection
    Plugins->>Cloud: Fetch CUR/Billing Data
    Cloud-->>Plugins: Cost Records
    Plugins-->>ScanEngine: Zombie Candidates

    ScanEngine->>LLM: Analyze Context
    LLM-->>ScanEngine: Recommendations

    ScanEngine->>API: Save Results
    API->>Slack: Send Alert
    Slack-->>User: Notification

    User->>Dashboard: Review & Approve
    Dashboard->>API: POST /remediate
    API->>Cloud: Execute Action
```

## Zero-API-Cost Architecture

```mermaid
flowchart LR
    subgraph "Traditional (Expensive)"
        CE[Cost Explorer API<br/>$0.01/request]
        CW[CloudWatch API<br/>$0.01/1000 requests]
        CL[CloudTrail API<br/>$2.00/100k events]
    end

    subgraph "Valdrix (Zero-Cost)"
        CUR[AWS CUR Export<br/>$0.00]
        RE[Resource Explorer<br/>$0.00]
        BQ[BigQuery Export<br/>Free Tier]
    end

    CE -.->|"$500+/month"| X((❌))
    CW -.->|"at scale"| X
    CL -.->|"at scale"| X

    CUR -->|"$0/month"| Y((✅))
    RE -->|"at scale"| Y
    BQ -->|"1TB free"| Y
```

## Multi-Tenant Security

```mermaid
flowchart TB
    subgraph "Request Flow"
        REQ[Incoming Request]
        JWT[JWT Validation]
        RLS[Row-Level Security]
        DATA[Tenant Data Only]
    end

    subgraph "Security Layers"
        STS[AWS STS<br/>Ephemeral Credentials]
        FERNET[Fernet Encryption<br/>Secrets at Rest]
        CSRF[CSRF Protection]
        RATE[Rate Limiting]
    end

    REQ --> JWT
    JWT --> RLS
    RLS --> DATA
    DATA --> STS
    STS --> FERNET
    JWT --> CSRF
    CSRF --> RATE
```

## Deployment Options

```mermaid
graph LR
    subgraph "Development"
        DEV[docker-compose up]
    end

    subgraph "Production"
        HELM[Helm Chart]
        K8S[Kubernetes]
        HPA[Auto-scaling]
    end

    subgraph "Monitoring"
        PROM2[Prometheus]
        GRAF2[Grafana]
        ALERT[Alertmanager]
    end

    DEV --> HELM
    HELM --> K8S
    K8S --> HPA
    K8S --> PROM2
    PROM2 --> GRAF2
    PROM2 --> ALERT
```
