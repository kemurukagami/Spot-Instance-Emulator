#!/usr/bin/env python3
"""
Start the head node server
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sie.head_node.main import app
from sie.common.constants import get_primary_ip
import uvicorn

if __name__ == "__main__":
    primary_ip = get_primary_ip()
    port = 8000
    
    print("Starting Spot Instance Emulator - Head Node")
    print("")
    print(f"External IP: {primary_ip}:{port}")
    print(f"WebSocket endpoint: ws://{primary_ip}:{port}/ws")
    print(f"Admin API: http://{primary_ip}:{port}/admin/")
    print(f"API Documentation: http://{primary_ip}:{port}/docs")
    print("")
    print("Updated Admin endpoints:")
    print("  GET  /admin/workers - List all connected workers")
    print("  GET  /admin/workers/unassigned - List workers available for assignment")
    print("  GET  /admin/instances - List all assigned instances")
    print("  POST /admin/assign-instance - Assign instance ID to worker")
    print("  POST /admin/unassign-instance - Unassign instance from worker")
    print("  POST /admin/interrupt - Trigger interruption (auto-unassigns)")
    print("")
    print("For other machines to connect:")
    print(f"  export HEAD_NODE_URL='ws://{primary_ip}:{port}/ws'")
    print(f"  python run_instance.py --head-node ws://{primary_ip}:{port}/ws")
    print("")
    
    uvicorn.run(app, host="0.0.0.0", port=port)