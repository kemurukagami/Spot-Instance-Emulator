#!/usr/bin/env python3
"""
Start the head node server
"""
import sys
import os
import argparse
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sie.head_node.main import app, set_trace_file
from sie.common.constants import get_primary_ip
import uvicorn

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Start the Spot Instance Emulator Head Node")
    parser.add_argument('--trace-file', type=str,
                       help='Path to trace CSV file for spot instance simulation')
    parser.add_argument('--simulation-speed', type=float, default=1.0,
                       help='Simulation speed multiplier (1.0 = real-time, 2.0 = 2x speed)')
    parser.add_argument('--instance-type', type=str,
                       help='Override instance type for all trace nodes (default: p3.8xlarge for p3-*.csv traces)')
    parser.add_argument('--port', type=int, default=8000,
                       help='Port to bind the server to (default: 8000)')
    parser.add_argument('--host', type=str, default="0.0.0.0",
                       help='Host to bind the server to (default: 0.0.0.0)')

    args = parser.parse_args()

    primary_ip = get_primary_ip()
    port = args.port

    print("Starting Spot Instance Emulator - Head Node")
    print("")

    # Configure trace simulation if specified
    if args.trace_file:
        trace_path = Path(args.trace_file)
        if not trace_path.exists():
            print(f"ERROR: Trace file not found: {args.trace_file}")
            sys.exit(1)

        print(f"Trace Simulation Enabled:")
        print(f"  Trace file: {args.trace_file}")
        print(f"  Simulation speed: {args.simulation_speed}x")
        if args.instance_type:
            print(f"  Instance type: {args.instance_type}")
        print("")

        # Set trace configuration in the main app
        set_trace_file(args.trace_file, args.simulation_speed, args.instance_type)

    print(f"External IP: {primary_ip}:{port}")
    print(f"WebSocket endpoint: ws://{primary_ip}:{port}/ws")
    print(f"Admin API: http://{primary_ip}:{port}/admin/")
    print(f"API Documentation: http://{primary_ip}:{port}/docs")
    print(f"Visualization Dashboard: http://{primary_ip}:{port}/visualization")
    print("")
    print("Admin endpoints:")
    print("  GET  /admin/workers - List all connected workers")
    print("  GET  /admin/workers/unassigned - List workers available for assignment")
    print("  GET  /admin/instances - List all assigned instances")
    print("  POST /admin/assign-instance - Assign instance ID to worker")
    print("  POST /admin/unassign-instance - Unassign instance from worker")
    print("  POST /admin/interrupt - Trigger interruption (auto-unassigns)")

    if args.trace_file:
        print("")
        print("Trace simulation endpoints:")
        print("  GET  /admin/simulation/status - Current simulation state")
        print("  POST /admin/simulation/pause - Pause trace playback")
        print("  POST /admin/simulation/resume - Resume trace playback")
        print("  GET  /admin/spot-instances/available - List available spot instances")
        print("  GET  /admin/spot-instances/assigned - List assigned spot instances")

    print("")
    print("For other machines to connect:")
    print(f"  export HEAD_NODE_URL='ws://{primary_ip}:{port}/ws'")
    print(f"  python run_instance.py --head-node ws://{primary_ip}:{port}/ws")
    print("")

    uvicorn.run(app, host=args.host, port=port)