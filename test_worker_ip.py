#!/usr/bin/env python3
"""
Test script to verify worker IP address detection.

This script checks if the head node correctly detects worker IP addresses
for SSH access configuration.

Usage:
1. Start head node: python run_head.py
2. Start worker: python run_instance.py --port 8001
3. Run this test: python test_worker_ip.py
"""

import asyncio
import aiohttp
import json

HEAD_NODE_URL = "http://localhost:8000"

async def test_worker_ip_detection():
    """Test worker IP address detection"""
    print("🔍 Testing Worker IP Address Detection")
    print("=" * 40)
    
    async with aiohttp.ClientSession() as session:
        try:
            # Get all workers
            async with session.get(f"{HEAD_NODE_URL}/admin/workers") as response:
                if response.status != 200:
                    print(f"❌ Failed to get workers: {response.status}")
                    return False
                
                workers = await response.json()
                
            print(f"Found {len(workers)} connected workers:")
            print()
            
            for worker in workers:
                worker_id = worker.get('worker_id', 'unknown')
                worker_ip = worker.get('worker_ip', 'not detected')
                connection_state = worker.get('connection_state', 'unknown')
                
                print(f"Worker: {worker_id}")
                print(f"  IP Address: {worker_ip}")
                print(f"  State: {connection_state}")
                print(f"  Connected: {worker.get('connected_at', 'unknown')}")
                
                # Analyze IP detection
                if worker_ip == 'not detected' or worker_ip is None:
                    print(f"  ⚠️  IP not detected - SSH will use localhost fallback")
                elif worker_ip in ['127.0.0.1', '::1', 'localhost']:
                    print(f"  ✅ Local connection detected - SSH will use localhost")
                elif worker_ip == 'unknown':
                    print(f"  ⚠️  IP detection failed - check WebSocket connection")
                else:
                    print(f"  ✅ Remote IP detected - SSH will use {worker_ip}")
                
                print()
            
            if not workers:
                print("❌ No workers connected!")
                print("Please start a worker with: python run_instance.py --port 8001")
                return False
            
            # Test with instance assignment to see SSH access info
            print("🧪 Testing SSH access info generation...")
            
            # For this test, we'll just show what would happen
            sample_worker = workers[0]
            print(f"Sample SSH access for worker {sample_worker['worker_id']}:")
            
            worker_ip = sample_worker.get('worker_ip', 'localhost')
            if worker_ip in ['127.0.0.1', '::1', None, 'unknown']:
                ssh_host = 'localhost'
            else:
                ssh_host = worker_ip
                
            print(f"  SSH Host: {ssh_host}")
            print(f"  SSH Command: ssh username@{ssh_host}")
            print()
            
            return True
            
        except Exception as e:
            print(f"❌ Test failed: {e}")
            return False

async def main():
    print("Note: This test requires a head node and at least one worker to be running.")
    print()
    
    success = await test_worker_ip_detection()
    
    if success:
        print("✅ Worker IP detection test completed!")
        print()
        print("For multi-machine deployment:")
        print("- Workers connecting from remote IPs will have their actual IP detected")
        print("- Users will get the correct SSH host for direct connection")
        print("- Local workers will use 'localhost' for SSH access")
    else:
        print("❌ Worker IP detection test failed!")

if __name__ == "__main__":
    asyncio.run(main())