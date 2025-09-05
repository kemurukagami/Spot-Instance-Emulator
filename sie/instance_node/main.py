from fastapi import FastAPI
import uvicorn
import asyncio
import logging
import uuid
import sys
import os
from datetime import datetime, timedelta
from sie.instance_node.core import HardwareDetector, WebSocketClient
from sie.instance_node.api import status_router, webhook_router, send_interruption_notice
from sie.instance_node.api.status import status
from sie.instance_node.api.webhook import webhook_config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(title="Spot Instance Emulator - Instance Node")

# Include routers
app.include_router(status_router)
app.include_router(webhook_router)

# Global WebSocket client
ws_client = None

@app.get("/")
async def root():
    return {"message": "Spot Instance Emulator Instance Node", "status": "running"}

async def interrupt_callback(warning_time: int, reason: str):
    """Handle interruption notification"""
    logger.warning(f"Interruption callback triggered: {warning_time}s warning")
    
    # Update status
    status.state = "interrupted"
    status.interruption_time = datetime.utcnow() + timedelta(seconds=warning_time)
    
    # Send webhook notification
    await send_interruption_notice(status.instance_id, warning_time, reason)

async def termination_callback():
    """Handle instance termination"""
    logger.info("Instance termination callback triggered - shutting down")
    status.state = "terminated"
    
    # Give a moment for final logging
    await asyncio.sleep(0.5)
    
    # Terminate the process
    logger.info("Instance node terminated due to spot interruption")
    os._exit(0)

async def start_websocket_client(head_node_url: str, instance_id: str, instance_type: str):
    """Start WebSocket connection to head node"""
    global ws_client
    
    # Detect hardware
    hardware_detector = HardwareDetector()
    hardware_profile = hardware_detector.detect_hardware()
    
    # Update status
    status.instance_id = instance_id
    status.instance_type = instance_type
    status.hardware = hardware_profile.dict()
    
    # Create and start WebSocket client
    ws_client = WebSocketClient(
        instance_id=instance_id,
        instance_type=instance_type,
        hardware_profile=hardware_profile.dict(),
        head_node_url=head_node_url,
        interrupt_callback=interrupt_callback,
        termination_callback=termination_callback
    )
    
    await ws_client.connect()

@app.on_event("startup")
async def startup_event():
    """Start WebSocket client on app startup"""
    # Get configuration from environment or defaults
    head_node_url = os.getenv("HEAD_NODE_URL", "ws://localhost:8000/ws")
    instance_id = os.getenv("INSTANCE_ID", f"i-{uuid.uuid4().hex[:12]}")
    instance_type = os.getenv("INSTANCE_TYPE", "t2.micro")
    
    # Configure webhook if provided
    webhook_url = os.getenv("WEBHOOK_URL")
    if webhook_url:
        webhook_config.url = webhook_url
        webhook_config.enabled = True
        logger.info(f"Webhook configured: {webhook_url}")
    
    logger.info(f"Starting instance node: {instance_id}")
    logger.info(f"Connecting to head node: {head_node_url}")
    
    # Start WebSocket client in background
    asyncio.create_task(start_websocket_client(head_node_url, instance_id, instance_type))

@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    if ws_client:
        await ws_client.disconnect()

if __name__ == "__main__":
    host = "0.0.0.0"
    port = int(os.getenv("INSTANCE_PORT", "8001"))
    logger.info(f"Starting Instance Node on {host}:{port}")
    uvicorn.run(app, host=host, port=port)