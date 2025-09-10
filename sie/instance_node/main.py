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
    """Handle instance unassignment (worker stays alive)"""
    logger.info("Instance unassignment callback triggered - clearing instance assignment")
    
    # Update status to reflect instance termination but worker continues
    status.instance_id = None
    status.instance_type = None
    status.state = "unassigned"
    status.interruption_time = None
    
    logger.info("Worker returned to unassigned state, ready for new instance assignment")

async def shutdown_callback():
    """Handle full process shutdown when connection to head node is lost"""
    logger.info("Connection to head node lost - shutting down worker process")
    
    # Give a moment for final logging
    await asyncio.sleep(0.5)
    
    # Terminate the entire process
    logger.info("Worker process terminated due to head node disconnection")
    os._exit(0)

async def start_websocket_client(head_node_url: str, worker_id: str):
    """Start WebSocket connection to head node"""
    global ws_client
    
    # Detect hardware
    hardware_detector = HardwareDetector()
    hardware_profile = hardware_detector.detect_hardware()
    
    # Update status to worker-based (no instance assigned initially)
    status.instance_id = None  # Will be assigned by head node
    status.instance_type = None
    status.worker_id = worker_id
    status.hardware = hardware_profile.dict()
    status.state = "unassigned"
    
    # Create and start WebSocket client
    ws_client = WebSocketClient(
        worker_id=worker_id,
        hardware_profile=hardware_profile.dict(),
        head_node_url=head_node_url,
        interrupt_callback=interrupt_callback,
        termination_callback=termination_callback,
        shutdown_callback=shutdown_callback
    )
    
    await ws_client.connect()

@app.on_event("startup")
async def startup_event():
    """Start WebSocket client on app startup"""
    # Get configuration from environment or defaults
    head_node_url = os.getenv("HEAD_NODE_URL", "ws://localhost:8000/ws")
    
    # Generate worker ID from machine characteristics
    hardware_detector = HardwareDetector()
    worker_id = hardware_detector.generate_worker_id()
    
    # Configure webhook if provided
    webhook_url = os.getenv("WEBHOOK_URL")
    if webhook_url:
        webhook_config.url = webhook_url
        webhook_config.enabled = True
        logger.info(f"Webhook configured: {webhook_url}")
    
    logger.info(f"Starting worker node: {worker_id}")
    logger.info(f"Connecting to head node: {head_node_url}")
    
    # Start WebSocket client in background
    asyncio.create_task(start_websocket_client(head_node_url, worker_id))

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