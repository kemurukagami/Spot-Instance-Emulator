from fastapi import APIRouter, BackgroundTasks
import aiohttp
import logging
from typing import Optional
from datetime import datetime, timedelta
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhook", tags=["webhook"])

class WebhookConfig(BaseModel):
    url: Optional[str] = None
    enabled: bool = False

webhook_config = WebhookConfig()

@router.post("/configure")
async def configure_webhook(config: WebhookConfig):
    """Configure user webhook for interruption notifications"""
    webhook_config.url = config.url
    webhook_config.enabled = config.enabled
    return {"status": "configured", "url": config.url}

async def send_interruption_notice(instance_id: str, warning_time: int, reason: str):
    """Send interruption notice to user webhook"""
    if not webhook_config.enabled or not webhook_config.url:
        logger.info("Webhook not configured, skipping notification")
        return
        
    termination_time = datetime.utcnow() + timedelta(seconds=warning_time)
    
    payload = {
        "action": "terminate",
        "time": termination_time.isoformat() + "Z",
        "instance_id": instance_id,
        "reason": reason,
        "warning_seconds": warning_time
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(webhook_config.url, json=payload, timeout=5) as response:
                if response.status == 200:
                    logger.info(f"Successfully sent interruption notice to {webhook_config.url}")
                else:
                    logger.error(f"Failed to send webhook: {response.status}")
    except Exception as e:
        logger.error(f"Error sending webhook: {e}")