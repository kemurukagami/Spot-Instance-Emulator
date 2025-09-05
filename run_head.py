#!/usr/bin/env python3
"""
Start the head node server
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sie.head_node.main import app
import uvicorn

if __name__ == "__main__":
    print("Starting Spot Instance Emulator - Head Node")
    print("API Documentation: http://localhost:8000/docs")
    print("Admin endpoints:")
    print("  GET  /admin/instances - List all instances")
    print("  POST /admin/interrupt - Trigger interruption")
    print("")
    uvicorn.run(app, host="0.0.0.0", port=8000)