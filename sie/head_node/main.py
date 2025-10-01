from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import uvicorn
import logging
import sys
import asyncio
import json
from typing import Optional, Set
from sie.head_node.core import PoolManager
from sie.head_node.core.trace_parser import TraceParser, parse_instance_type_from_filename
from sie.head_node.core.simulation_controller import SimulationController
from sie.head_node.api import ConnectionManager, admin_router
from sie.head_node.api.admin import managers
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
connection_manager = ConnectionManager(pool_manager)

# Trace simulation (will be initialized if trace file provided)
simulation_controller: Optional[SimulationController] = None

# Visualization WebSocket connections
visualization_connections: Set[WebSocket] = set()

# Store managers for admin API
managers.pool_manager = pool_manager
managers.connection_manager = connection_manager

# Include admin router
app.include_router(admin_router)

# Mount static files for visualization
app.mount("/static", StaticFiles(directory="static"), name="static")

def set_trace_file(trace_file: str, simulation_speed: float = 1.0, instance_type: Optional[str] = None) -> None:
    """Configure trace simulation (called from run_head.py)"""
    global simulation_controller

    try:
        # Determine instance type
        if instance_type is None:
            instance_type = parse_instance_type_from_filename(trace_file)

        # Parse trace file
        logger.info(f"Loading trace file: {trace_file}")
        trace_simulator = TraceParser.parse_trace_file(trace_file, instance_type)
        trace_simulator.simulation_speed = simulation_speed

        # Validate trace
        warnings = TraceParser.validate_trace(trace_simulator)
        for warning in warnings:
            logger.warning(f"Trace validation: {warning}")

        # Create simulation controller
        simulation_controller = SimulationController(pool_manager, trace_simulator)

        # Set up callbacks for real-time visualization updates
        simulation_controller.on_spot_instance_added = on_spot_instance_added
        simulation_controller.on_spot_instance_removed = on_spot_instance_removed

        # Store for admin API
        managers.simulation_controller = simulation_controller

        logger.info("Trace simulation configured successfully")

    except Exception as e:
        logger.error(f"Failed to configure trace simulation: {e}")
        raise

@app.on_event("startup")
async def startup_event():
    """Start trace simulation if configured"""
    if simulation_controller:
        logger.info("Starting trace simulation...")
        await simulation_controller.start_simulation()

@app.on_event("shutdown")
async def shutdown_event():
    """Stop trace simulation on shutdown"""
    if simulation_controller:
        logger.info("Stopping trace simulation...")
        await simulation_controller.stop_simulation()

async def on_spot_instance_added(spot_instance_id: str, instance_type: str) -> None:
    """Callback for when a spot instance is added from trace"""
    await broadcast_to_visualization({
        "type": "spot_instance_added",
        "data": {
            "spot_instance_id": spot_instance_id,
            "instance_type": instance_type
        }
    })

async def on_spot_instance_removed(spot_instance_id: str, unassigned_worker: Optional[str]) -> None:
    """Callback for when a spot instance is removed from trace"""
    await broadcast_to_visualization({
        "type": "spot_instance_removed",
        "data": {
            "spot_instance_id": spot_instance_id,
            "unassigned_worker": unassigned_worker
        }
    })

async def broadcast_to_visualization(message: dict) -> None:
    """Broadcast message to all connected visualization clients"""
    if not visualization_connections:
        return

    disconnected = set()
    for websocket in visualization_connections:
        try:
            await websocket.send_text(json.dumps(message))
        except Exception:
            disconnected.add(websocket)

    # Remove disconnected clients
    visualization_connections.difference_update(disconnected)

@app.get("/")
async def root():
    status = {"message": "Spot Instance Emulator Head Node", "status": "running"}
    if simulation_controller:
        status["trace_simulation"] = simulation_controller.get_simulation_status()
    return status

@app.get("/visualization")
async def get_visualization():
    """Serve the visualization dashboard"""
    return FileResponse("static/index.html")

@app.websocket("/visualization")
async def visualization_websocket(websocket: WebSocket):
    """WebSocket endpoint for real-time visualization updates"""
    await websocket.accept()
    visualization_connections.add(websocket)
    logger.info("Visualization client connected")

    try:
        while True:
            # Wait for messages from client
            message = await websocket.receive_text()
            data = json.loads(message)

            if data.get("type") == "request_update":
                # Send current state to client
                await send_visualization_update(websocket)

    except WebSocketDisconnect:
        visualization_connections.discard(websocket)
        logger.info("Visualization client disconnected")
    except Exception as e:
        logger.error(f"Visualization WebSocket error: {e}")
        visualization_connections.discard(websocket)

async def send_visualization_update(websocket: WebSocket) -> None:
    """Send current state to visualization client"""
    try:
        # Get simulation status (use managers if available, fallback to global)
        active_controller = managers.simulation_controller or simulation_controller
        if active_controller:
            sim_status = active_controller.get_simulation_status()
            await websocket.send_text(json.dumps({
                "type": "simulation_status",
                "data": sim_status
            }))

            # Get upcoming events
            events = active_controller.get_upcoming_events(20)
            await websocket.send_text(json.dumps({
                "type": "upcoming_events",
                "data": [
                    {
                        "timestamp_ms": event.timestamp_ms,
                        "action": event.action,
                        "node_id": event.node_id
                    }
                    for event in events
                ]
            }))

        # Get workers
        workers = pool_manager.get_all_workers()
        worker_data = []
        for worker in workers:
            worker_info = {
                "worker_id": worker.worker_id,
                "connection_state": worker.connection_state,
                "hardware": worker.hardware,
                "connected_at": worker.connected_at.isoformat(),
                "last_heartbeat": worker.last_heartbeat.isoformat(),
                "assigned_instance": None
            }

            # Get assigned instance
            instance = pool_manager.get_instance_for_worker(worker.worker_id)
            if instance:
                worker_info["assigned_instance"] = instance.instance_id

            worker_data.append(worker_info)

        await websocket.send_text(json.dumps({
            "type": "workers",
            "data": worker_data
        }))

        # Get spot instances
        available_spots = pool_manager.get_available_spot_instances()
        assigned_spots = pool_manager.get_assigned_spot_instances()

        spot_data = {
            "available": [
                {
                    "spot_instance_id": spot.spot_instance_id,
                    "instance_type": spot.instance_type,
                    "available_since": spot.available_since.isoformat(),
                    "is_assigned": spot.is_assigned
                }
                for spot in available_spots
            ],
            "assigned": [
                {
                    "spot_instance_id": spot.spot_instance_id,
                    "instance_type": spot.instance_type,
                    "available_since": spot.available_since.isoformat(),
                    "assigned_worker_id": spot.assigned_worker_id,
                    "is_assigned": spot.is_assigned
                }
                for spot in assigned_spots
            ]
        }

        await websocket.send_text(json.dumps({
            "type": "spot_instances",
            "data": spot_data
        }))

    except Exception as e:
        logger.error(f"Error sending visualization update: {e}")

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