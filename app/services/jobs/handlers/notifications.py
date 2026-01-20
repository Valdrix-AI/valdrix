"""
Notification and Webhook Job Handlers
"""
from typing import Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.background_job import BackgroundJob
from app.services.jobs.handlers.base import BaseJobHandler


class NotificationHandler(BaseJobHandler):
    """Handle notification job (Slack, Email, etc.)."""
    
    async def execute(self, job: BackgroundJob, db: AsyncSession) -> Dict[str, Any]:
        from app.services.notifications import get_slack_service
        
        payload = job.payload or {}
        message = payload.get("message")
        title = payload.get("title", "Valdrix Notification")
        severity = payload.get("severity", "info")
        
        if not message:
            raise ValueError("message required for notification")
        
        service = get_slack_service()
        if not service:
            return {"status": "skipped", "reason": "slack_not_configured"}
            
        success = await service.send_alert(title=title, message=message, severity=severity)
        
        return {"status": "completed", "success": success}


class WebhookRetryHandler(BaseJobHandler):
    """Handle webhook retry job (e.g., Paystack)."""
    
    async def execute(self, job: BackgroundJob, db: AsyncSession) -> Dict[str, Any]:
        payload = job.payload or {}
        provider = payload.get("provider", "generic")
        
        if provider == "paystack":
            from app.services.billing.webhook_retry import process_paystack_webhook
            return await process_paystack_webhook(job, db)
        
        # Generic HTTP webhook retry
        import httpx
        
        url = payload.get("url")
        data = payload.get("data")
        headers = payload.get("headers", {})
        
        if not url:
            raise ValueError("url required for generic webhook_retry")
        
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=data, headers=headers, timeout=30)
            response.raise_for_status()
        
        return {"status": "completed", "status_code": response.status_code}
