<p align="center">
  <img src="assets/valdrix_icon.png" alt="Valdrix" width="200" />
</p>

<h1 align="center">Valdrix</h1>
<h3 align="center">Optimize Cloud Value, Not Just Cost</h3>

<p align="center">
  <em><strong>Value + Matrix</strong> — A FinOps engine that continuously optimizes cloud value<br/>
  by eliminating waste, controlling cost, and reducing unnecessary overhead.</em>
</p>

<p align="center">
  <a href="https://github.com/Valdrix-AI/valdrix/actions/workflows/ci.yml"><img src="https://github.com/Valdrix-AI/valdrix/actions/workflows/ci.yml/badge.svg" alt="CI/CD Status" /></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-BSL%201.1-blue.svg" alt="License: BSL 1.1" /></a>
  <a href="https://python.org"><img src="https://img.shields.io/badge/Python-3.12-3776AB.svg?logo=python&logoColor=white" alt="Python 3.12" /></a>
  <a href="https://svelte.dev"><img src="https://img.shields.io/badge/Svelte-5-FF3E00.svg?logo=svelte&logoColor=white" alt="Svelte 5" /></a>
  <a href="https://fastapi.tiangolo.com"><img src="https://img.shields.io/badge/FastAPI-0.128+-009688.svg?logo=fastapi&logoColor=white" alt="FastAPI" /></a>
  <a href="https://foundation.greensoftware.foundation/"><img src="https://img.shields.io/badge/GreenOps-Enabled-2ea44f.svg" alt="GreenOps" /></a>
</p>

<p align="center">
  <strong><a href="#-the-problem">The Problem</a></strong> · 
  <strong><a href="#-the-solution">The Solution</a></strong> · 
  <strong><a href="#-features">Features</a></strong> · 
  <strong><a href="#-get-started">Get Started</a></strong> · 
  <strong><a href="#-roadmap">Roadmap</a></strong>
</p>

---

## 💸 The Problem

> **"We're spending $47,000/month on AWS... and I can't explain where 30% of it goes."**  
> — *Every engineering manager at some point*

Here's what the industry knows but rarely admits:

- **$164 billion** in cloud spend was wasted in 2024. *(Flexera State of the Cloud Report)*
- **30-35%** of cloud resources are idle, orphaned, or oversized. *(Gartner)*
- The average company has **no idea** what a developer spin-up costs until the monthly invoice arrives.

And it's not just money. Every idle EC2 instance, every orphan EBS volume, every forgotten load balancer is **burning electricity** and **emitting CO₂** for absolutely nothing.

Most FinOps tools give you dashboards.  
Dashboards give you graphs.  
Graphs give you... more questions.

**You don't need more graphs. You need actionable value insights.**

---

## 🛡️ The Solution

**Valdrix transforms raw cost data into actionable value intelligence.**

It connects to your cloud, uncovers waste, explains spend behavior, and gives you *exactly* what to do—with receipts.

<p align="center">
  <img src="https://img.shields.io/badge/Turn_Spend_Into-Business_Value-blueviolet?style=for-the-badge" alt="Turn Spend Into Business Value" />
</p>

### Here's how it works:

1. **Connect** → One-click AWS IAM role setup. Read-only. Zero secrets stored.
2. **Scan** → Our 11 zombie-detection plugins sweep your account every day.
3. **Reason** → The LLM brain (GPT-4o, Claude 3.5, Groq, Gemini) analyzes context, not just metrics.
4. **Act** → Get Slack alerts, approve remediations, and watch your bill shrink.

> [!TIP]
> **Zero API Costs for Your AWS Account**: Valdrix uses [AWS CUR](https://docs.aws.amazon.com/cur/latest/userguide/what-is-cur.html) and [Resource Explorer 2](https://docs.aws.amazon.com/resource-explorer/latest/userguide/welcome.html) instead of expensive APIs like Cost Explorer ($0.01/request). Your AWS bill from Valdrix scans is **~$0.00/month**.


```
              ┌──────────────────┐
              │   Your Cloud ☁️  │
              └────────┬─────────┘
                       ▼
              ┌──────────────────┐
              │  🔌 Valdrix Core │
              │    (FastAPI)     │
              └────────┬─────────┘
                       ▼
   ┌───────────────────┴───────────────────┐
   │           Zombie Detection            │
   │  EC2 · EBS · S3 · RDS · NAT · ELB    │
   │  SageMaker · Redshift · ECR · EIPs   │
   └───────────────────┬───────────────────┘
                       ▼
              ┌──────────────────┐
              │   🧠 LLM Brain   │
              │  (Multi-Model)   │
              └────────┬─────────┘
                       ▼
   ┌───────────────────┴───────────────────┐
   │          Slack Alerts + Dashboard     │
   │         (Approve / Reject / Act)      │
   └───────────────────────────────────────┘
```

---

## ✨ Features

### 🧟 **Deep Zombie Detection**
Not just "idle EC2." We find *everything*:

| Category | What We Hunt | Precision Signals |
|----------|--------------|-------------------|
| **Compute** | Idle EC2, Azure VMs, GCP Instances | **GPU Hunting** (P/G/Nvidia), **Owner Attribution** |
| **Storage** | Orphan EBS, Managed Disks, Snapshots | **Creator Attribution**, Age-based decay |
| **Network** | Unallocated IPs, Orphan LBs, NAT GWs | **Association Tracking** |
| **Data** | Idle RDS, Redshift, GCP SQL | **Connection Activity** |
| **Registry** | Stale ECR, ACR, GCR Images | **Pull Frequency** |

**11 detection plugins + Multi-Cloud Parity (AWS, Azure, GCP).**

---

### 🧠 **AI That Actually Thinks**

Other tools use static rules: *"CPU < 10% for 7 days = zombie."*

Valdrix asks: *"Why did RDS costs spike 47% on Tuesday?"*  
And answers: *"Because Staging-DB-04 was left running after the load test. Estimated waste: $312/month."*

**Powered by your choice of:**
- OpenAI (GPT-4o, GPT-4o-mini)
- Anthropic (Claude 3.5 Sonnet)
- Google (Gemini 2.0 Flash)
- Groq (Llama 3.3 70B — fast and cheap)

**Bring Your Own Key (BYOK) supported.** Keep your API costs in your own account.

---

### 🌿 **GreenOps Native**

Every wasted dollar has a carbon cost. Valdrix calculates it.

```
Total CO₂ this month:      42.7 kg
Equivalent to:             105 miles driven  🚗
Trees needed to offset:    1.9 trees  🌳
Carbon efficiency:         89 gCO₂e per $1 spent
```

**Region recommendations included.** Move to `us-west-2` and cut emissions by 94%.

---

### 🔔 **Slack-First Alerts**

Your engineering team lives in Slack. So does Valdrix.

- **Anomaly alerts** when costs spike unexpectedly
- **Daily digests** with top savings opportunities
- **Leaderboards** — "Who saved the most this week?"
- **One-click approve/reject** for remediations

---

### 🔁 **Workflow Automation (GitHub/GitLab/CI)**

Trigger runbooks directly from policy/remediation events:

- `policy.block` / `policy.escalate` / `remediation.completed`
- Native dispatch to GitHub Actions and GitLab CI
- Generic CI webhook fallback
- Deterministic evidence links embedded in event payloads

See configuration details in `docs/integrations/workflow_automation.md`.

---

### 🛡️ **Enterprise-Grade Security**

We're paranoid, so you don't have to be:

- **Zero-Trust Architecture** — We assume IAM roles via STS. No long-lived credentials.
- **Read-Only by Default** — Our CloudFormation/Terraform templates grant only `Describe*` and `Get*` permissions.
- **Human-in-the-Loop** — The AI recommends; *you* approve the action.
- **GitOps-First Remediation** — Generate professional Terraform plans (`state rm` and `removed` blocks) to decommission resources via your existing CI/CD.
- **Audit Trail** — Every remediation request is logged with who requested, who approved, and when.

---

## 🚀 Get Started

### Prerequisites
- Docker & Docker Compose
- An AWS account with:
  - AWS CUR configured to deliver Parquet reports to S3
  - Resource Explorer 2 enabled
- Cost Explorer is optional (Valdrix ingestion path is CUR + Resource Explorer 2)
- An LLM API key (OpenAI, Anthropic, Google, or Groq)

### Runtime Dependency Policy (Prod/Staging)
- `tiktoken` is required for accurate token accounting and LLM budget enforcement.
- If `SENTRY_DSN` is configured, `sentry-sdk` is required.
- `prophet` is required by default in staging/production.
- Temporary break-glass fallback is allowed only with:
  - `FORECASTER_ALLOW_HOLT_WINTERS_FALLBACK=true`
  - `FORECASTER_BREAK_GLASS_REASON` (auditable justification)
  - `FORECASTER_BREAK_GLASS_EXPIRES_AT` (ISO-8601 UTC expiry)

### 1. Clone & Configure

```bash
git clone https://github.com/Valdrix-AI/valdrix.git
cd valdrix
cp .env.example .env
```

Edit `.env` and add:
```env
DATABASE_URL=postgresql+asyncpg://...
OPENAI_API_KEY=sk-...  # or GROQ_API_KEY, etc.
SUPABASE_JWT_SECRET=your-jwt-secret
```

### 2. Start the Stack

```bash
docker-compose up -d
```

### 3. Open the Dashboard

- **API Docs:** [http://localhost:8000/docs](http://localhost:8000/docs)
- **Dashboard:** [http://localhost:5173](http://localhost:5173)

### 4. Connect Your AWS Account

The dashboard will guide you through deploying our read-only IAM role via CloudFormation or Terraform. Takes 60 seconds.

---

## 📊 Tech Stack

| Layer | Technology |
|-------|------------|
| **Backend** | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy (async) |
| **Frontend** | SvelteKit (Svelte 5 Runes), TailwindCSS v4, Shadcn-Svelte |
| **Database** | PostgreSQL (Neon), Supabase Auth |
| **LLM** | LangChain, OpenAI, Anthropic, Google Genai, Groq |
| **Infra** | Docker, Kubernetes (Helm), GitHub Actions, Prometheus |
| **Observability** | OpenTelemetry, Grafana Dashboards, Prometheus Metrics |
| **GreenOps** | CodeCarbon integration |

---

## 🏗️ Production Infrastructure

Valdrix includes production-ready infrastructure components:

### Kubernetes Deployment
```bash
# Deploy with Helm
helm install valdrix helm/valdrix/ \
  --set image.tag=latest \
  --set existingSecrets.name=valdrix-secrets

# Or customize values
helm install valdrix helm/valdrix/ -f my-values.yaml
```

### Pre-configured Components
| Component | Location | Description |
|-----------|----------|-------------|
| **Helm Chart** | `helm/valdrix/` | Full K8s deployment (HPA, Ingress, Service) |
| **K8s Manifests** | `k8s/` | Raw YAML manifests for non-Helm deploys |
| **Grafana Dashboards** | `grafana/dashboards/` | API Overview + FinOps metrics |
| **Load Tests** | `loadtest/` | k6 + Locust performance tests |
| **SBOM Generation** | `.github/workflows/sbom.yml` | CycloneDX + vulnerability scanning |

### CI/CD Pipeline
- ✅ **Linting**: Ruff + MyPy
- ✅ **Testing**: Pytest with coverage
- ✅ **Security**: Bandit (SAST), Trivy (containers), TruffleHog (secrets)
- ✅ **GreenOps**: CodeCarbon emissions tracking
- ✅ **E2E**: Playwright browser tests

---

## 🗺️ Roadmap

We're in **active development**. Here's where we are:

### ✅ Done
- [x] Multi-tenant AWS onboarding (CloudFormation + Terraform)
- [x] 11 zombie detection plugins
- [x] Multi-LLM analysis (OpenAI, Claude, Gemini, Groq)
- [x] Carbon footprint calculator with regional intensity
- [x] Slack integration (alerts, digests, leaderboards)
- [x] SvelteKit dashboard with dark mode
- [x] Human-in-the-loop remediation workflow
- [x] **Azure & GCP support** (Adapters complete)
- [x] **ML-based forecasting** (Prophet-integrated)
- [x] **ActiveOps** (Autonomous Remediation Engine)

### 🔨 In Progress
- [ ] FinOps-as-Code (GitHub Action to preview cost changes on PRs)
- [ ] Real-time WebSocket updates
- [ ] Deployment to Koyeb

### 🔮 Coming Soon
- [ ] ClickHouse migration (for 100M+ scaling)
- [ ] Stripe billing & usage metering
- [ ] Virtual tagging (LLM infers team ownership)

---

## 📜 License

Valdrix is **source available** under the **Business Source License (BSL) 1.1**.

- ✅ **Free for internal use** — Run it on your own infrastructure.
- ❌ **No resale** — Cannot offer Valdrix as a managed service.
- 🗓️ **Freedom date:** Converts to **Apache 2.0** on **January 12, 2029**.

See [LICENSE](LICENSE) for full terms.

Additional policy docs:
- [Licensing FAQ](docs/licensing.md#licensing-faq)
- [Commercial Licensing](COMMERCIAL_LICENSE.md)
- [Trademark Policy](TRADEMARK_POLICY.md)
- [Contributor License Agreement (CLA)](CLA.md)
- [Open-Core Boundary](docs/open_core_boundary.md)
- [Tenancy ADR](docs/architecture/ADR-0001-tenancy-model.md)
- [Pricing Metric Model](docs/pricing_model.md)

---

## 🤝 Contributing

We welcome contributions! Please read our [CONTRIBUTING.md](CONTRIBUTING.md) before opening a PR.



---

## 💖 Support

If Valdrix saved your team $1,000 this month, consider sponsoring the project:

<p align="center">
  <a href="https://github.com/sponsors/daretechie">
    <img src="https://img.shields.io/badge/💜-Sponsor%20on%20GitHub-pink?style=for-the-badge" alt="Sponsor" />
  </a>
</p>

---

<p align="center">
  Built with obsessive attention to detail by <a href="https://github.com/daretechie"><strong>Dare AbdulGoniyy</strong></a>.<br/>
  <em>Because your cloud bill shouldn't keep you up at night.</em>
</p>
