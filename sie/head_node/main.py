from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import uvicorn
import logging
import sys
from sie.head_node.core import PoolManager
from sie.head_node.api import ConnectionManager, admin_router
from sie.head_node.api.admin import managers

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
connection_manager = ConnectionManager(pool_manager)

# Store managers for admin API
managers.pool_manager = pool_manager
managers.connection_manager = connection_manager

# Include admin router
app.include_router(admin_router)

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
    logger.info(f"Starting Head Node on {host}:{port}")
    uvicorn.run(app, host=host, port=port)