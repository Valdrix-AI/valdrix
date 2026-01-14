<p align="center">
  <img src="assets/valdrix_icon.png" alt="Valdrix" width="200" />
</p>

<h1 align="center">Valdrix</h1>
<h3 align="center">Intelligence for Cloud Value Optimization</h3>

<p align="center">
  <em>Valdrix combines <strong>Value</strong> + <strong>Matrix</strong>: an intelligent system that extracts,<br/>
  measures, and optimizes value from complex multi-cloud financial data.</em>
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

**You don't need more graphs. You need answers.**

---

## 🛡️ The Solution

**Valdrix is different.**

It's not a dashboard. It's an **autonomous value optimization engine** that connects to your cloud, finds value leakage, and tells you *exactly* what to do—with receipts.

<p align="center">
  <img src="https://img.shields.io/badge/Think_of_it_as-�_Your_Cloud_Value_Intelligence-blueviolet?style=for-the-badge" alt="Cloud Value Intelligence" />
</p>

### Here's how it works:

1. **Connect** → One-click AWS IAM role setup. Read-only. Zero secrets stored.
2. **Scan** → Our 11 zombie-detection plugins sweep your account every day.
3. **Reason** → The LLM brain (GPT-4o, Claude 3.5, Groq, Gemini) analyzes context, not just metrics.
4. **Act** → Get Slack alerts, approve remediations, and watch your bill shrink.

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

| Category | What We Hunt |
|----------|--------------|
| **Compute** | Idle EC2 instances, forgotten SageMaker endpoints |
| **Storage** | Orphan EBS volumes, snapshots older than 90 days, empty S3 buckets |
| **Network** | Unallocated Elastic IPs, orphan load balancers, underused NAT gateways |
| **Data** | Idle RDS instances, cold Redshift clusters |
| **Registry** | Legacy ECR images with no recent pulls |

**11 detection plugins.** More coming.

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

### 🛡️ **Enterprise-Grade Security**

We're paranoid, so you don't have to be:

- **Zero-Trust Architecture** — We assume IAM roles via STS. No long-lived credentials.
- **Read-Only by Default** — Our CloudFormation/Terraform templates grant only `Describe*` and `Get*` permissions.
- **Human-in-the-Loop** — The AI recommends; *you* approve the action.
- **Audit Trail** — Every remediation request is logged with who requested, who approved, and when.

---

## 🚀 Get Started

### Prerequisites
- Docker & Docker Compose
- An AWS account (with Cost Explorer enabled)
- An LLM API key (OpenAI, Anthropic, Google, or Groq)

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
| **Infra** | Docker, GitHub Actions, Prometheus |
| **GreenOps** | CodeCarbon integration |

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

### 🔨 In Progress
- [ ] FinOps-as-Code (GitHub Action to preview cost changes on PRs)
- [ ] Real-time WebSocket updates
- [ ] Deployment to Koyeb

### 🔮 Coming Soon
- [ ] Azure & GCP support
- [ ] ML-based forecasting (Prophet/ARIMA)
- [ ] Virtual tagging (LLM infers team ownership)
- [ ] Stripe billing & usage metering

---

## 📜 License

Valdrix is **source available** under the **Business Source License (BSL) 1.1**.

- ✅ **Free for internal use** — Run it on your own infrastructure.
- ❌ **No resale** — Cannot offer Valdrix as a managed service.
- 🗓️ **Freedom date:** Converts to **Apache 2.0** on **January 12, 2029**.

See [LICENSE](LICENSE) for full terms.

---

## 🤝 Contributing

We welcome contributions! Please read our [CONTRIBUTING.md](CONTRIBUTING.md) before opening a PR.

**Areas we need help:**
- Azure & GCP adapters
- More zombie detection plugins
- Dashboard UI/UX improvements
- Documentation

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
