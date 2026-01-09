from datetime import date
from typing import List, Dict, Any, Annotated
from fastapi import FastAPI, Depends, Query, Header, HTTPException
from app.core.config import get_settings
from app.core.logging import setup_logging
import structlog
from app.services.adapters.base import CostAdapter
from app.services.adapters.aws import AWSAdapter
from app.services.llm.factory import LLMFactory
from app.services.llm.analyzer import FinOpsAnalyzer
from app.services.scheduler import SchedulerService
from prometheus_fastapi_instrumentator import Instrumentator
from contextlib import asynccontextmanager
import secrets
from app.core.auth import get_current_user, CurrentUser
from app.api.v1.onboard import router as onboard_router
from app.api.connections import router as connections_router
from app.api.settings import router as settings_router
from app.api.leaderboards import router as leaderboards_router
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.services.carbon.calculator import CarbonCalculator
from app.services.zombies.detector import ZombieDetector, RemediationService
from app.models.remediation import RemediationAction
from app.models.llm import LLMUsage
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional
from uuid import UUID


# Configure logging
setup_logging()

# Get logger
logger = structlog.get_logger()

# Dependency Factory
def get_cost_adapter() -> CostAdapter:
  return AWSAdapter()

# This runs BEFORE the app starts (setup) and AFTER it stops (teardown).
@asynccontextmanager
async def lifespan(app: FastAPI):
  # Setup: Connect to DB, load AI model, etc
  settings = get_settings()
  logger.info(f"Loading {settings.APP_NAME} config...")

  # Initialize scheduler
  scheduler = SchedulerService()
  scheduler.start()
  app.state.scheduler = scheduler # Store scheduler in app state for health checks

  yield

  # Teardown: Disconnect from DB, etc
  logger.info(f"Shutting down {settings.APP_NAME}...")
  # Stop scheduler
  scheduler.stop()

# 2. Create the app instance
settings = get_settings()

app = FastAPI(
  title=settings.APP_NAME,
  version=settings.VERSION,
  lifespan=lifespan)

# Initialize Prometheus Metrics
Instrumentator().instrument(app).expose(app)

# CORS Middleware - Allow frontend dashboard to access API
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",       # SvelteKit dev server
        "http://localhost:5174",       # SvelteKit alt port
        "http://127.0.0.1:5173",
        "http://127.0.0.1:5174",
        "http://localhost:3000",       # Alternative dev port
        # Add production URLs here later
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(onboard_router)
app.include_router(connections_router)
app.include_router(settings_router)
app.include_router(leaderboards_router)

# 3. Health Check (The Heartbeat of the app)
# Every K8s pod needs a health check endpoint to prove it's alive
@app.get("/health")
async def health_check():
  scheduler_status = app.state.scheduler.get_status()
  return {
    "status": "active",
    "app": settings.APP_NAME,
    "version": settings.VERSION,
    "scheduler": scheduler_status,
  }

@app.get("/costs", response_model=List[Dict[str, Any]])
async def get_costs(
  start_date: date,
  end_date: date,
  adapter: Annotated[CostAdapter, Depends(get_cost_adapter)],
  user: Annotated[CurrentUser, Depends(get_current_user)]
):
  """
  Retrieves daily cloud costs for a specified date range.

  This endpoint uses the `CostAdapter` dependency (Strategy Pattern) to fetch data from the 
  configured cloud provider (currently AWS).

  Args:
      start_date (date): The start date for the cost period (inclusive).
      end_date (date): The end date for the cost period (exclusive).
      adapter (CostAdapter): The injected cloud provider adapter.
      user (CurrentUser): The authenticated user.

  Returns:
      List[Dict[str, Any]]: A list of daily cost records.
  """
  logger.info("fetching_costs", start=start_date, end=end_date, user_id=str(user.id))
  return await adapter.get_daily_costs(start_date, end_date)

# Dependency Factory for LLM
def get_llm_provider() -> str:
  settings = get_settings()
  return settings.LLM_PROVIDER

def get_analyzer(provider: str = Depends(get_llm_provider)) -> FinOpsAnalyzer:
  llm = LLMFactory.create(provider)
  return FinOpsAnalyzer(llm)

@app.get("/analyze")
async def analyze_costs(
    start_date: date,
    end_date: date,
    adapter: Annotated[CostAdapter, Depends(get_cost_adapter)],
    analyzer: Annotated[FinOpsAnalyzer, Depends(get_analyzer)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),              # <--- Add this
    provider: str = Depends(get_llm_provider),       # <--- Add this
):
    """
    Analyzes cloud costs using GenAI to identify anomalies and savings.
    """
    logger.info("starting_sentinel_analysis", start=start_date, end=end_date)
    
    # Step 1: Get cost data
    cost_data = await adapter.get_daily_costs(start_date, end_date)
    
    # Step 2: Analyze with AI (and track usage)
    insights = await analyzer.analyze(
        cost_data,
        tenant_id=user.tenant_id,  # <--- Pass context
        db=db,                     # <--- Pass context
        provider=provider,         # <--- Record provider
    )
    
    return {"analysis": insights}

@app.post("/admin/trigger-analysis")
async def trigger_analysis(x_admin_key: str = Header(..., alias="X-Admin-Key")):
    """
    Manually trigger a scheduled analysis job.
    Requires X-Admin-Key header matching ADMIN_API_KEY environment variable.
    """
    settings = get_settings()
    
    if not settings.ADMIN_API_KEY:
        logger.error("admin_key_not_configured")
        raise HTTPException(
            status_code=503, 
            detail="Admin endpoint not configured. Set ADMIN_API_KEY."
        )
    
    if not secrets.compare_digest(x_admin_key, settings.ADMIN_API_KEY):
        logger.warning("admin_auth_failed", provided_key_prefix=x_admin_key[:4] + "***")
        raise HTTPException(status_code=403, detail="Forbidden")
    
    logger.info("manual_trigger_requested")
    await app.state.scheduler.daily_analysis_job()
    return {"status": "triggered", "message": "Daily analysis job executed."}


@app.get("/llm/usage")
async def get_llm_usage(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=50, le=200),
):
    """
    Get LLM usage history for the tenant.
    
    Returns token counts, costs, and model usage.
    """
    result = await db.execute(
        select(LLMUsage)
        .where(LLMUsage.tenant_id == user.tenant_id)
        .order_by(LLMUsage.created_at.desc())
        .limit(limit)
    )
    records = result.scalars().all()
    
    return {
        "usage": [
            {
                "id": str(r.id),
                "model": r.model,
                "provider": r.provider,
                "input_tokens": r.input_tokens,
                "output_tokens": r.output_tokens,
                "total_tokens": r.total_tokens,
                "cost_usd": float(r.cost_usd) if r.cost_usd else 0,
                "request_type": r.request_type,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in records
        ],
        "count": len(records),
    }

@app.get("/carbon")
async def get_carbon_footprint(
    start_date: date,
    end_date: date,
    adapter: Annotated[CostAdapter, Depends(get_cost_adapter)],
    user: Annotated[CurrentUser, Depends(get_current_user)],
    region: str = Query(default="us-east-1", description="AWS region for carbon intensity"),
):
    """
    Calculate carbon footprint from AWS usage.
    
    Returns CO₂ emissions estimate based on cost data and region.
    """
    logger.info("calculating_carbon", start=start_date, end=end_date, region=region)
    
    # Get cost data
    cost_data = await adapter.get_daily_costs(start_date, end_date)
    
    # Calculate carbon
    calculator = CarbonCalculator()
    result = calculator.calculate_from_costs(cost_data, region=region)
    
    return result

@app.get("/zombies")
async def scan_zombies(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    region: str = Query(default="us-east-1"),
):
    """
    Scan AWS account for zombie resources (unused/underutilized).
    
    Returns unattached volumes, old snapshots, unused Elastic IPs.
    Sends Slack alert if zombies are detected (based on user settings).
    """
    logger.info("scanning_zombies", region=region)
    detector = ZombieDetector(region=region)
    zombies = await detector.scan_all()
    
    # Count total zombies found
    zombie_count = (
        len(zombies.get("unattached_volumes", [])) +
        len(zombies.get("old_snapshots", [])) +
        len(zombies.get("unused_elastic_ips", []))
    )
    
    # Send Slack alert if zombies detected
    if zombie_count > 0:
        settings = get_settings()
        if settings.SLACK_BOT_TOKEN and settings.SLACK_CHANNEL_ID:
            try:
                from app.services.notifications import SlackService
                slack = SlackService(settings.SLACK_BOT_TOKEN, settings.SLACK_CHANNEL_ID)
                
                # Estimate potential savings
                estimated_savings = sum(
                    v.get("estimated_monthly_cost", 0) 
                    for v in zombies.get("unattached_volumes", [])
                )
                
                await slack.send_alert(
                    title="Zombie Resources Detected!",
                    message=(
                        f"Found *{zombie_count} zombie resources* that may be costing you money:\n\n"
                        f"• Unattached volumes: {len(zombies.get('unattached_volumes', []))}\n"
                        f"• Old snapshots: {len(zombies.get('old_snapshots', []))}\n"
                        f"• Unused Elastic IPs: {len(zombies.get('unused_elastic_ips', []))}\n\n"
                        f"💰 Estimated savings: *${estimated_savings:.2f}/month*\n\n"
                        f"Review and clean up in the CloudSentinel dashboard."
                    ),
                    severity="warning" if zombie_count < 5 else "critical"
                )
                logger.info("zombie_slack_alert_sent", count=zombie_count)
            except Exception as e:
                logger.error("zombie_slack_alert_failed", error=str(e))
    
    return zombies


# --- Remediation Request Models ---
class RemediationRequestCreate(BaseModel):
    """Request to create a new remediation request."""
    resource_id: str
    resource_type: str
    action: str  # delete_volume, delete_snapshot, release_elastic_ip
    estimated_savings: float
    create_backup: bool = False
    backup_retention_days: int = 30
    backup_cost_estimate: float = 0


class ReviewRequest(BaseModel):
    """Request to approve/reject a remediation."""
    notes: Optional[str] = None


# --- Remediation Approval Workflow Endpoints ---

@app.post("/zombies/request")
async def create_remediation_request(
    request: RemediationRequestCreate,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
    region: str = Query(default="us-east-1"),
):
    """
    Create a remediation request (pending approval).
    
    Human-in-the-loop: This does NOT execute immediately.
    Request must be approved before execution.
    """
    # Map string action to enum
    try:
        action_enum = RemediationAction(request.action)
    except ValueError:
        raise HTTPException(400, f"Invalid action: {request.action}")
    
    service = RemediationService(db=db, region=region)
    result = await service.create_request(
        tenant_id=user.tenant_id,
        user_id=user.id,
        resource_id=request.resource_id,
        resource_type=request.resource_type,
        action=action_enum,
        estimated_savings=request.estimated_savings,
        create_backup=request.create_backup,
        backup_retention_days=request.backup_retention_days,
        backup_cost_estimate=request.backup_cost_estimate,
    )
    
    return {
        "status": "pending",
        "request_id": str(result.id),
        "message": "Request created. Awaiting approval.",
        "backup_enabled": request.create_backup,
    }


@app.get("/zombies/pending")
async def list_pending_requests(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
    region: str = Query(default="us-east-1"),
):
    """
    List all pending remediation requests for the tenant. 
    """
    service = RemediationService(db=db, region=region)
    pending = await service.list_pending(user.tenant_id)
    
    return {
        "pending_count": len(pending),
        "requests": [
            {
                "id": str(r.id),
                "resource_id": r.resource_id,
                "resource_type": r.resource_type,
                "action": r.action.value,
                "estimated_savings": float(r.estimated_monthly_savings) if r.estimated_monthly_savings else 0,
                "create_backup": r.create_backup,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in pending
        ],
    }


@app.post("/zombies/approve/{request_id}")
async def approve_remediation(
    request_id: UUID,
    review: ReviewRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
    region: str = Query(default="us-east-1"),
):
    """
    Approve a pending remediation request.
    
    After approval, the request can be executed.
    """
    service = RemediationService(db=db, region=region)
    
    try:
        result = await service.approve(
            request_id=request_id,
            reviewer_id=user.id,
            notes=review.notes,
        )
        return {
            "status": "approved",
            "request_id": str(result.id),
            "message": "Request approved. Ready for execution.",
        }
    except ValueError as e:
        raise HTTPException(404, str(e))


@app.post("/zombies/reject/{request_id}")
async def reject_remediation(
    request_id: UUID,
    review: ReviewRequest,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
    region: str = Query(default="us-east-1"),
):
    """
    Reject a pending remediation request.
    """
    service = RemediationService(db=db, region=region)
    
    try:
        result = await service.reject(
            request_id=request_id,
            reviewer_id=user.id,
            notes=review.notes,
        )
        return {
            "status": "rejected",
            "request_id": str(result.id),
            "message": "Request rejected.",
        }
    except ValueError as e:
        raise HTTPException(404, str(e))


@app.post("/zombies/execute/{request_id}")
async def execute_remediation(
    request_id: UUID,
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db),
    region: str = Query(default="us-east-1"),
):
    """
    Execute an approved remediation request.
    
    ⚠️ THIS WILL DELETE RESOURCES.
    
    If backup was requested, a snapshot will be created first.
    """
    service = RemediationService(db=db, region=region)
    
    try:
        result = await service.execute(request_id=request_id)
        
        response = {
            "status": result.status.value,
            "request_id": str(result.id),
            "resource_id": result.resource_id,
        }
        
        if result.backup_resource_id:
            response["backup_id"] = result.backup_resource_id
            response["message"] = f"Resource deleted. Backup created: {result.backup_resource_id}"
        elif result.status.value == "completed":
            response["message"] = "Resource deleted successfully."
        else:
            response["error"] = result.execution_error
        
        return response
        
    except ValueError as e:
        raise HTTPException(400, str(e))


