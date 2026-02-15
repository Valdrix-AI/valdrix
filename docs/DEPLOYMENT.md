# Valdrix Deployment Guide

Deploy Valdrix for **$0/month** using Supabase, Vercel, and Koyeb.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                        VERCEL                               │
│                   (SvelteKit Dashboard)                     │
│                    dashboard.valdrix.ai                     │
└─────────────────────┬───────────────────────────────────────┘
                      │ API Calls
                      ▼
┌─────────────────────────────────────────────────────────────┐
│                        KOYEB                                │
│                   (FastAPI Backend)                         │
│                     api.valdrix.ai                          │
└─────────────────────┬───────────────────────────────────────┘
                      │ SQL + Auth
                      ▼
┌─────────────────────────────────────────────────────────────┐
│                       SUPABASE                              │
│              (PostgreSQL + Auth + RLS)                      │
└─────────────────────────────────────────────────────────────┘
```

---

## Step 1: Supabase Setup (Database + Auth)

### 1.1 Create Project
1. Go to [supabase.com](https://supabase.com) and sign up
2. Click **New Project**
3. Name: `valdrix-prod`
4. Database Password: Generate a strong one and **save it**
5. Region: Choose closest to your users (e.g., `us-east-1`)

### 1.2 Get Connection String
1. Go to **Project Settings** → **Database**
2. Copy the **Connection string (URI)** under "Connection Pooling"
3. It looks like: `postgresql://postgres.[ref]:[password]@aws-0-us-east-1.pooler.supabase.com:6543/postgres`

> [!IMPORTANT]
> Use the **pooler** connection string (port 6543), not the direct one (port 5432).
> This is required for serverless environments like Koyeb.

### 1.3 Get Auth JWT Secret
1. Go to **Project Settings** → **API**
2. Copy the **JWT Secret** (under "JWT Settings")

### 1.4 Configure Auth Providers (Optional)
1. Go to **Authentication** → **Providers**
2. Enable **Google**, **GitHub**, or **Email/Password** as needed

---

## Step 2: Get API Keys

### 2.1 Groq (Free LLM)
1. Go to [console.groq.com](https://console.groq.com)
2. Sign up and create an API key
3. Free tier: ~30 requests/min with Llama 3.3 70B

### 2.2 Encryption Key
Generate a secure key for encrypting AWS credentials at rest:
```bash
openssl rand -hex 32
```

### 2.3 Admin API Key
Create a secret password for admin endpoints:
```bash
openssl rand -hex 16
```

---

## Step 3: Deploy Backend to Koyeb

### 3.1 Create Koyeb Account
1. Go to [koyeb.com](https://koyeb.com) and sign up
2. Connect your GitHub account

### 3.2 Create New Service
1. Click **Create Service** → **Web Service**
2. Select **GitHub** and choose your `valdrix` repository
3. Configure:
   - **Builder**: Docker
   - **Dockerfile path**: `Dockerfile`
   - **Port**: `8000`

### 3.3 Set Environment Variables
Add these in Koyeb's dashboard under **Environment Variables**:

| Variable | Value | Notes |
|----------|-------|-------|
| `DATABASE_URL` | `postgresql://postgres.[ref]...` | From Supabase Step 1.2 |
| `SUPABASE_JWT_SECRET` | `your-jwt-secret` | From Supabase Step 1.3 |
| `ENCRYPTION_KEY` | `your-64-char-hex` | From Step 2.2 |
| `ADMIN_API_KEY` | `your-admin-key` | From Step 2.3 |
| `LLM_PROVIDER` | `groq` | Free LLM provider |
| `GROQ_API_KEY` | `gsk_...` | From Step 2.1 |
| `CORS_ORIGINS` | `["https://your-vercel-app.vercel.app"]` | Update after Vercel deploy |
| `SAAS_STRICT_INTEGRATIONS` | `true` | Recommended for multi-tenant SaaS mode |

### 3.4 Deploy
1. Click **Deploy**
2. Wait for build to complete (~3-5 minutes)
3. Note your service URL: `https://valdrix-xxx.koyeb.app`

> In strict SaaS mode, tenant integrations (Jira/workflows/channels) are configured in-app, not via backend env vars.

### 3.5 Run Database Migrations
After deployment, run migrations via Koyeb's console or locally:
```bash
# Option A: Run locally against production DB
DATABASE_URL="your-supabase-url" alembic upgrade head

# Option B: Add a one-time job in Koyeb
# Command: alembic upgrade head
```

---

## Step 4: Deploy Frontend to Vercel

### 4.1 Create Vercel Account
1. Go to [vercel.com](https://vercel.com) and sign up
2. Connect your GitHub account

### 4.2 Import Project
1. Click **Add New** → **Project**
2. Select your `valdrix` repository
3. Configure:
   - **Framework Preset**: SvelteKit
   - **Root Directory**: `dashboard`

### 4.3 Set Environment Variables
Add these in Vercel's dashboard:

| Variable | Value |
|----------|-------|
| `PUBLIC_API_URL` | `https://valdrix-xxx.koyeb.app` |
| `PUBLIC_SUPABASE_URL` | `https://xxx.supabase.co` |
| `PUBLIC_SUPABASE_ANON_KEY` | `eyJhbG...` (from Supabase API settings) |

### 4.4 Deploy
1. Click **Deploy**
2. Wait for build (~1-2 minutes)
3. Note your URL: `https://valdrix.vercel.app`

### 4.5 Update CORS on Koyeb
Go back to Koyeb and update `CORS_ORIGINS`:
```
["https://valdrix.vercel.app"]
```

---

## Step 5: Verify Deployment

### 5.1 Health Check
```bash
curl https://valdrix-xxx.koyeb.app/health
```

Expected response:
```json
{
  "status": "active",
  "app": "Valdrix",
  "version": "0.1.0",
  "scheduler": {"running": true, "jobs": ["daily_finops_scan", "weekly_remediation_sweep"]}
}
```

### 5.2 Test Authentication
1. Open `https://valdrix.vercel.app`
2. Sign up with email or OAuth
3. Verify you can access the dashboard

### 5.3 Test AWS Connection
1. Go to Settings → AWS Connections
2. Add your AWS Role ARN
3. Verify the connection

---

## Custom Domain Setup (Optional)

### Vercel (Frontend)
1. Go to **Project Settings** → **Domains**
2. Add `app.valdrix.ai`
3. Update DNS: CNAME → `cname.vercel-dns.com`

### Koyeb (Backend)
1. Go to **Service Settings** → **Domains**
2. Add `api.valdrix.ai`
3. Update DNS: CNAME → provided by Koyeb

### Update Environment Variables
After custom domains:
- Koyeb: `CORS_ORIGINS=["https://app.valdrix.ai"]`
- Vercel: `PUBLIC_API_URL=https://api.valdrix.ai`

---

## Troubleshooting

### Database Connection Issues
- Ensure you're using the **pooler** connection (port 6543)
- Check that your IP is not blocked in Supabase

### Auth Errors
- Verify `SUPABASE_JWT_SECRET` matches exactly
- Check that the JWT hasn't expired

### Scheduler Not Running
- Koyeb free tier keeps services awake (unlike Render)
- Check logs: `valdrix_scheduler_job_runs_total` metric

### CORS Errors
- Ensure `CORS_ORIGINS` includes your exact frontend URL
- Include the protocol (`https://`)

---

## Cost Summary

| Service | Free Tier Limit | Overage Cost |
|---------|-----------------|--------------|
| Supabase | 500MB DB, 50K auth users | $25/mo Pro |
| Koyeb | 2 nano instances, 100GB bandwidth | $5.50/mo per instance |
| Vercel | 100GB bandwidth, 6000 min/mo | $20/mo Pro |
| Groq | ~30 req/min | Usage-based |

**Total: $0/month** until you scale beyond free tiers.
