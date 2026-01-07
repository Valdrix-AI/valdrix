# CloudSentinel AI 🤖🛡️

**The Autonomous FinOps Guardian for Multi-Cloud Infrastructure**

[![CI/CD Status](https://github.com/daretechie/CloudSentinel-AI/actions/workflows/ci.yml/badge.svg)](https://github.com/daretechie/CloudSentinel-AI/actions)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/release/python-3120/)
[![Docker Image Size](https://img.shields.io/badge/docker%20image-256MB-green)](https://hub.docker.com/)

CloudSentinel AI is an **autonomous agent** that proactively monitors cloud infrastructure costs, detects anomalies using Generative AI (LLMs), and identifies "zombie resources" (idle assets).

It is built with **FAANG-level rigor**, featuring Clean Architecture, Strategy Pattern for multi-cloud support, and a comprehensive DevOps pipeline.

---

## 🏗️ Architecture

The system follows **Clean Architecture** principles to ensure maintainability and testability.

```mermaid
graph TD
    Scheduler[APScheduler Service] -->|Trigger| API[FastAPI Core]
    API -->|Fetch Data| Adapter[CostAdapter Interface]
    Adapter -->|Impl| AWS[AWS Adapter (Boto3)]
    Adapter -->|Impl| Azure[Azure Adapter (Future)]
    
    API -->|Analyze| Brain[FinOpsAnalyzer]
    Brain -->|Prompt| LLM[LLM Factory]
    LLM -->|Request| OpenAI[OpenAI / Groq / Claude]
    
    Scheduler -->|Metrics| Prom[Prometheus]
```

### Key Design Decisions
*   **Strategy Pattern:** `CostAdapter` interface allows seamless switching between AWS, Azure, and GCP without changing core logic.
*   **Factory Pattern:** `LLMFactory` abstracts the underlying AI provider (OpenAI, Claude, Groq), enabling vendor-agnostic intelligence.
*   **Dependency Injection:** All services are injected via FastAPI's `Depends`, making unit testing with mocks trivial.
*   **Autonomous Operation:** `APScheduler` runs background jobs to analyze costs daily without human intervention.
*   **Observability:** Built-in `structlog` (structured logging) and `Prometheus` metrics for production-grade monitoring.

---

## 🚀 Features

*   **Multi-Cloud Ready:** Abstracted adapter layer for AWS (implemented), Azure, and GCP.
*   **AI-Powered Analysis:** Uses LLM to detect anomalies ("Why did S3 cost spike 30%?") and zombie resources.
*   **Strict JSON Output:** The AI Agent is prompted to return machine-readable JSON for integration with dashboards.
*   **Security First:** 
    *   Explicit credential handling (no implicit auth).
    *   Trivy vulnerability scanning in CI/CD.
    *   Non-root Docker container.
*   **Production Ready:**
    *   Multi-stage Docker build (256MB).
    *   CI/CD pipeline with GitHub Actions.
    *   Health checks and Metrics endpoints.

---

## 🛠️ Tech Stack

*   **Language:** Python 3.12
*   **Framework:** FastAPI
*   **AI Orchestration:** LangChain
*   **Cloud SDK:** Boto3 (AWS)
*   **Scheduling:** APScheduler (AsyncIO)
*   **Observability:** Prometheus, Structlog
*   **DevOps:** Docker, GitHub Actions, Poetry

---

## 🏃‍♂️ Quick Start

### Prerequisites
*   Python 3.12+
*   Docker
*   AWS Credentials

### 1. Clone & Configure
```bash
git clone https://github.com/daretechie/CloudSentinel-AI.git
cd CloudSentinel-AI
cp .env.example .env
```

Edit `.env` with your API keys:
```ini
AWS_ACCESS_KEY_ID=your_key
AWS_SECRET_ACCESS_KEY=your_secret
LLM_PROVIDER=groq
GROQ_API_KEY=your_groq_key
```

### 2. Run with Docker (Recommended)
```bash
# Build the production image
docker build -t cloudsentinel:latest .

# Run the sentinel
docker run --rm -p 8000:8000 --env-file .env cloudsentinel:latest
```
Visit `http://localhost:8000/docs` to see the API.

### 3. Run Locally (Dev)
```bash
poetry install
poetry run uvicorn app.main:app --reload
```

---

## 🧪 Testing

We use `pytest` for unit testing. The CI pipeline runs these automatically.

```bash
poetry run pytest
```
*   **Coverage:** 100% of Adapter logic is covered using `unittest.mock` (no real AWS calls made during tests).

---

## 📊 Observability

*   **Health Check:** `GET /health`
*   **Prometheus Metrics:** `GET /metrics`
*   **Structured Logs:** stdout (JSON format)

---

## 🔮 Future Roadmap

*   [ ] Azure & GCP Adapters
*   [ ] Terraform (IaC) for EKS Deployment
*   [ ] Slack/Teams Webhooks for Alerts

---
**License**: MIT
