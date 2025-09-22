#!/usr/bin/env python3
"""
Test script to validate the new worker-based instance lifecycle.

This script tests the state transitions:
unassigned → assigned → interrupted → unassigned

Usage:
1. Start head node: python run_head.py
2. Start instance node: python run_instance.py --port 8001  
3. Run this test: python test_lifecycle.py

Expected behavior:
1. Worker connects as 'unassigned'
2. Admin assigns instance ID → worker becomes 'assigned'
3. Admin triggers interruption → worker becomes 'interrupted'
4. After warning time → worker returns to 'unassigned'
"""

import asyncio
import aiohttp
import json
import time
from typing import Dict, Any

HEAD_NODE_URL = "http://localhost:8000"
INSTANCE_NODE_URL = "http://localhost:8001"

async def make_request(session: aiohttp.ClientSession, method: str, url: str, **kwargs) -> Dict[Any, Any]:
    """Make HTTP request and return JSON response"""
    async with session.request(method, url, **kwargs) as response:
        if response.status >= 400:
            text = await response.text()
            raise Exception(f"{method} {url} failed: {response.status} - {text}")
        return await response.json()

async def test_lifecycle():
    """Test the complete worker lifecycle"""
    async with aiohttp.ClientSession() as session:
        print("🧪 Testing Worker-Based Instance Lifecycle")
        print("=" * 50)
        
        # Step 1: Check initial state
        print("\n1. Checking initial state...")
        workers = await make_request(session, "GET", f"{HEAD_NODE_URL}/admin/workers")
        instances = await make_request(session, "GET", f"{HEAD_NODE_URL}/admin/instances")
        
        print(f"   Workers connected: {len(workers)}")
        print(f"   Instances assigned: {len(instances)}")
        
        if len(workers) == 0:
            print("   ❌ No workers connected. Please start instance node first!")
            return False
            
        worker = workers[0]
        worker_id = worker["worker_id"]
        print(f"   Worker ID: {worker_id}")
        print(f"   Worker state: {worker['connection_state']}")
        
        if worker['connection_state'] != 'unassigned':
            print(f"   ❌ Expected worker to be 'unassigned', got '{worker['connection_state']}'")
            return False
        print("   ✅ Worker is in 'unassigned' state")
        
        # Step 2: Assign instance
        print("\n2. Assigning instance to worker...")
        response = await make_request(session, "POST", f"{HEAD_NODE_URL}/admin/assign-instance", 
                                    json={"worker_id": worker_id, "instance_type": "m5.large"})
        
        instance_id = response["instance_id"]
        print(f"   Assigned instance: {instance_id}")
        
        # Wait a moment for state to propagate
        await asyncio.sleep(1)
        
        # Check worker state
        workers = await make_request(session, "GET", f"{HEAD_NODE_URL}/admin/workers")
        worker = next(w for w in workers if w["worker_id"] == worker_id)
        print(f"   Worker state: {worker['connection_state']}")
        
        if worker['connection_state'] != 'assigned':
            print(f"   ❌ Expected worker to be 'assigned', got '{worker['connection_state']}'")
            return False
        print("   ✅ Worker is in 'assigned' state")
        
        # Check instance node status
        instance_status = await make_request(session, "GET", f"{INSTANCE_NODE_URL}/instance/status")
        print(f"   Instance node shows: instance_id={instance_status.get('instance_id')}, state={instance_status.get('state')}")
        
        if instance_status.get('state') != 'assigned':
            print(f"   ⚠️  Instance node state is '{instance_status.get('state')}', expected 'assigned'")
        
        # Step 3: Trigger interruption
        print("\n3. Triggering interruption...")
        await make_request(session, "POST", f"{HEAD_NODE_URL}/admin/interrupt",
                         json={"instance_id": instance_id, "warning_time": 5})  # 5 second warning
        
        # Wait a moment for state to propagate
        await asyncio.sleep(1)
        
        # Check worker state
        workers = await make_request(session, "GET", f"{HEAD_NODE_URL}/admin/workers")
        worker = next(w for w in workers if w["worker_id"] == worker_id)
        print(f"   Worker state: {worker['connection_state']}")
        
        if worker['connection_state'] != 'interrupted':
            print(f"   ❌ Expected worker to be 'interrupted', got '{worker['connection_state']}'")
            return False
        print("   ✅ Worker is in 'interrupted' state")
        
        # Check instance node status
        instance_status = await make_request(session, "GET", f"{INSTANCE_NODE_URL}/instance/status")
        print(f"   Instance node shows: state={instance_status.get('state')}")
        
        # Step 4: Wait for auto-unassignment
        print("\n4. Waiting for auto-unassignment (5 seconds)...")
        for i in range(6):
            print(f"   Waiting... {i+1}s")
            await asyncio.sleep(1)
        
        # Check final state
        workers = await make_request(session, "GET", f"{HEAD_NODE_URL}/admin/workers")
        worker = next(w for w in workers if w["worker_id"] == worker_id)
        instances = await make_request(session, "GET", f"{HEAD_NODE_URL}/admin/instances")
        
        print(f"   Worker state: {worker['connection_state']}")
        print(f"   Instances assigned: {len(instances)}")
        
        if worker['connection_state'] != 'unassigned':
            print(f"   ❌ Expected worker to be 'unassigned', got '{worker['connection_state']}'")
            return False
        print("   ✅ Worker returned to 'unassigned' state")
        
        if len(instances) > 0:
            print(f"   ❌ Expected no instances, but found {len(instances)}")
            return False
        print("   ✅ Instance was unassigned")
        
        # Check instance node status
        instance_status = await make_request(session, "GET", f"{INSTANCE_NODE_URL}/instance/status")
        print(f"   Instance node shows: instance_id={instance_status.get('instance_id')}, state={instance_status.get('state')}")
        
        if instance_status.get('instance_id') is not None:
            print(f"   ⚠️  Instance node still shows instance_id, expected None")
        if instance_status.get('state') != 'unassigned':
            print(f"   ⚠️  Instance node state is '{instance_status.get('state')}', expected 'unassigned'")
        
        print("\n🎉 All tests passed! State transitions working correctly:")
        print("   unassigned → assigned → interrupted → unassigned")
        return True

async def main():
    try:
        success = await test_lifecycle()
        if success:
            print("\n✅ Test completed successfully!")
        else:
            print("\n❌ Test failed!")
            exit(1)
    except Exception as e:
        print(f"\n💥 Test error: {e}")
        exit(1)

if __name__ == "__main__":
    asyncio.run(main())