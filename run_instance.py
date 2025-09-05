#!/usr/bin/env python3
"""
Start an instance node
"""
import sys
import os
import argparse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sie.instance_node.main import app
import uvicorn

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Start an instance node")
    parser.add_argument("--port", type=int, default=8001, help="Port to run on")
    parser.add_argument("--instance-id", help="Instance ID (auto-generated if not provided)")
    parser.add_argument("--instance-type", default="t2.micro", help="Instance type")
    parser.add_argument("--head-node", default="ws://localhost:8000/ws", help="Head node WebSocket URL")
    parser.add_argument("--webhook-url", help="Webhook URL for interruption notifications")
    
    args = parser.parse_args()
    
    # Set environment variables
    os.environ["INSTANCE_PORT"] = str(args.port)
    if args.instance_id:
        os.environ["INSTANCE_ID"] = args.instance_id
    os.environ["INSTANCE_TYPE"] = args.instance_type
    os.environ["HEAD_NODE_URL"] = args.head_node
    if args.webhook_url:
        os.environ["WEBHOOK_URL"] = args.webhook_url
    
    print(f"Starting Spot Instance Emulator - Instance Node")
    print(f"Instance Type: {args.instance_type}")
    print(f"Head Node: {args.head_node}")
    print(f"API Port: {args.port}")
    print(f"Instance endpoints: http://localhost:{args.port}/instance/status")
    print("")
    
    uvicorn.run(app, host="0.0.0.0", port=args.port)