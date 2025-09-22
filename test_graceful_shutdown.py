#!/usr/bin/env python3
"""
Test script to verify graceful shutdown when head node disconnects.

This script:
1. Starts a worker and connects to head node
2. Stops the head node process 
3. Verifies the worker shuts down gracefully

Usage:
1. Start head node: python run_head.py
2. Start instance node: python run_instance.py --port 8001
3. Run this test: python test_graceful_shutdown.py
"""

import asyncio
import aiohttp
import signal
import subprocess
import time
import os

HEAD_NODE_URL = "http://localhost:8000"

async def test_graceful_shutdown():
    """Test graceful shutdown when head node disconnects"""
    print("🧪 Testing Graceful Shutdown on Head Node Disconnection")
    print("=" * 55)
    
    async with aiohttp.ClientSession() as session:
        # Step 1: Verify worker is connected
        print("\n1. Checking worker connection...")
        try:
            async with session.get(f"{HEAD_NODE_URL}/admin/workers") as response:
                if response.status == 200:
                    workers = await response.json()
                    print(f"   ✅ Workers connected: {len(workers)}")
                    if len(workers) > 0:
                        worker_id = workers[0]["worker_id"]
                        print(f"   Worker ID: {worker_id}")
                    else:
                        print("   ❌ No workers connected. Please start instance node first!")
                        return False
                else:
                    print(f"   ❌ Failed to connect to head node: {response.status}")
                    return False
        except Exception as e:
            print(f"   ❌ Failed to connect to head node: {e}")
            return False
        
        # Step 2: Find head node process
        print("\n2. Finding head node process...")
        try:
            # Find the head node process
            result = subprocess.run(['pgrep', '-f', 'run_head.py'], 
                                  capture_output=True, text=True)
            if result.returncode == 0 and result.stdout.strip():
                head_pid = int(result.stdout.strip().split('\n')[0])
                print(f"   Head node PID: {head_pid}")
            else:
                print("   ❌ Could not find head node process")
                return False
        except Exception as e:
            print(f"   ❌ Error finding head node process: {e}")
            return False
        
        # Step 3: Terminate head node
        print("\n3. Terminating head node...")
        try:
            os.kill(head_pid, signal.SIGTERM)
            print("   ✅ Sent SIGTERM to head node")
        except Exception as e:
            print(f"   ❌ Error terminating head node: {e}")
            return False
        
        # Step 4: Wait and check if worker process is still running
        print("\n4. Checking if worker shuts down gracefully...")
        
        # Wait a few seconds for shutdown
        for i in range(5):
            print(f"   Waiting... {i+1}s")
            await asyncio.sleep(1)
        
        # Check if instance node process is still running
        try:
            result = subprocess.run(['pgrep', '-f', 'run_instance.py'], 
                                  capture_output=True, text=True)
            if result.returncode == 0 and result.stdout.strip():
                instance_pids = result.stdout.strip().split('\n')
                print(f"   ⚠️  Instance node processes still running: {instance_pids}")
                print("   This might be expected if using run_in_background or if shutdown is still in progress")
                
                # Give it a bit more time
                await asyncio.sleep(2)
                
                # Check again
                result = subprocess.run(['pgrep', '-f', 'run_instance.py'], 
                                      capture_output=True, text=True)
                if result.returncode == 0 and result.stdout.strip():
                    print("   ❌ Worker did not shut down gracefully")
                    return False
                else:
                    print("   ✅ Worker shut down gracefully (after delay)")
                    return True
            else:
                print("   ✅ Worker shut down gracefully")
                return True
                
        except Exception as e:
            print(f"   ❌ Error checking worker process: {e}")
            return False

async def main():
    print("Note: This test will terminate your running head node!")
    print("Make sure you have a worker running before proceeding.")
    print("")
    
    try:
        success = await test_graceful_shutdown()
        if success:
            print("\n✅ Graceful shutdown test passed!")
            print("Workers properly shut down when head node disconnects.")
        else:
            print("\n❌ Graceful shutdown test failed!")
    except Exception as e:
        print(f"\n💥 Test error: {e}")

if __name__ == "__main__":
    asyncio.run(main())