from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import uvicorn
import logging
import sys
from sie.head_node.core import PoolManager
from sie.head_node.core.user_manager import UserManager
from sie.head_node.api import ConnectionManager, admin_router
from sie.head_node.api.admin import managers
from sie.head_node.api import auth, instances
from sie.common.constants import get_primary_ip

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(title="Spot Instance Emulator - Head Node")

# Initialize managers
pool_manager = PoolManager()
user_manager = UserManager()
connection_manager = ConnectionManager(pool_manager)

# Store managers for admin API
managers.pool_manager = pool_manager
managers.connection_manager = connection_manager

# Store managers for auth API
auth.user_manager = user_manager
instances.user_manager = user_manager
instances.pool_manager = pool_manager
instances.connection_manager = connection_manager

# Include routers
app.include_router(admin_router)
app.include_router(auth.router)
app.include_router(instances.router)

@app.get("/")
async def root():
    return {"message": "Spot Instance Emulator Head Node", "status": "running"}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for instance connections"""
    connection_id = await connection_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_json()
            await connection_manager.handle_message(connection_id, data)
    except WebSocketDisconnect:
        connection_manager.disconnect(connection_id)
        logger.info(f"Instance disconnected: {connection_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        connection_manager.disconnect(connection_id)

if __name__ == "__main__":
    host = "0.0.0.0"
    port = 8000
    primary_ip = get_primary_ip()
    
    logger.info(f"Starting Head Node")
    logger.info(f"Binding to: {host}:{port}")
    logger.info(f"External IP: {primary_ip}:{port}")
    logger.info(f"")
    logger.info(f"WebSocket endpoint: ws://{primary_ip}:{port}/ws")
    logger.info(f"Admin API: http://{primary_ip}:{port}/admin/")
    logger.info(f"Interactive docs: http://{primary_ip}:{port}/docs")
    logger.info(f"")
    logger.info(f"For other machines to connect:")
    logger.info(f"  export HEAD_NODE_URL='ws://{primary_ip}:{port}/ws'")
    logger.info(f"  python run_instance.py --head-node ws://{primary_ip}:{port}/ws")
    
    uvicorn.run(app, host=host, port=port)