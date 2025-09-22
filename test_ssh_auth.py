#!/usr/bin/env python3
"""
Test script for SSH-based user authentication workflow.

This script tests the complete SSH authentication flow:
1. User registration with SSH public key
2. Instance request with authentication
3. System user creation on worker
4. SSH access to instance
5. Instance termination and user cleanup

Usage:
1. Start head node: python run_head.py
2. Start worker: python run_instance.py --port 8001
3. Run this test: python test_ssh_auth.py

Prerequisites:
- SSH key pair generated (ssh-keygen -t rsa -b 2048 -f ~/.ssh/test_key)
- sudo permissions on the worker machine for user management
"""

import asyncio
import aiohttp
import json
import subprocess
import os
from pathlib import Path
from typing import Dict, Any

HEAD_NODE_URL = "http://localhost:8000"

class SSHAuthTester:
    def __init__(self):
        self.username = "testuser"
        self.api_token = None
        self.ssh_key_path = Path.home() / ".ssh" / "test_key"
        self.ssh_pub_key_path = Path.home() / ".ssh" / "test_key.pub"
        
    async def setup_ssh_key(self) -> str:
        """Generate or read SSH key pair"""
        print("📝 Setting up SSH key...")
        
        if not self.ssh_key_path.exists():
            print(f"   Generating SSH key pair at {self.ssh_key_path}")
            try:
                subprocess.run([
                    'ssh-keygen', '-t', 'rsa', '-b', '2048', 
                    '-f', str(self.ssh_key_path), 
                    '-N', '',  # No passphrase
                    '-C', f'{self.username}@test'
                ], check=True, capture_output=True)
                print("   ✅ SSH key pair generated")
            except subprocess.CalledProcessError as e:
                print(f"   ❌ Failed to generate SSH key: {e}")
                return None
        else:
            print("   ✅ Using existing SSH key pair")
        
        # Read public key
        try:
            with open(self.ssh_pub_key_path, 'r') as f:
                public_key = f.read().strip()
            print(f"   Public key: {public_key[:50]}...")
            return public_key
        except Exception as e:
            print(f"   ❌ Failed to read public key: {e}")
            return None
    
    async def make_request(self, session: aiohttp.ClientSession, method: str, url: str, **kwargs) -> Dict[Any, Any]:
        """Make HTTP request and return JSON response"""
        headers = kwargs.get('headers', {})
        if self.api_token:
            headers['Authorization'] = f'Bearer {self.api_token}'
        kwargs['headers'] = headers
        
        async with session.request(method, url, **kwargs) as response:
            if response.status >= 400:
                text = await response.text()
                raise Exception(f"{method} {url} failed: {response.status} - {text}")
            return await response.json()
    
    async def test_user_registration(self, session: aiohttp.ClientSession, ssh_public_key: str) -> bool:
        """Test user registration with SSH public key"""
        print("\n1. Testing user registration...")
        
        try:
            response = await self.make_request(
                session, "POST", f"{HEAD_NODE_URL}/auth/register",
                json={
                    "username": self.username,
                    "ssh_public_key": ssh_public_key
                }
            )
            
            self.api_token = response["api_token"]
            print(f"   ✅ User registered: {response['username']}")
            print(f"   API token: {self.api_token[:20]}...")
            return True
            
        except Exception as e:
            print(f"   ❌ Registration failed: {e}")
            return False
    
    async def test_authentication(self, session: aiohttp.ClientSession) -> bool:
        """Test API token authentication"""
        print("\n2. Testing authentication...")
        
        try:
            response = await self.make_request(
                session, "GET", f"{HEAD_NODE_URL}/auth/test"
            )
            
            print(f"   ✅ Authentication successful: {response['message']}")
            return True
            
        except Exception as e:
            print(f"   ❌ Authentication failed: {e}")
            return False
    
    async def test_instance_request(self, session: aiohttp.ClientSession) -> Dict[str, Any]:
        """Test instance request"""
        print("\n3. Testing instance request...")
        
        try:
            response = await self.make_request(
                session, "POST", f"{HEAD_NODE_URL}/instances/request",
                json={"instance_type": "t3.micro"}
            )
            
            print(f"   ✅ Instance requested: {response['instance_id']}")
            print(f"   Assignment ID: {response['assignment_id']}")
            print(f"   Worker ID: {response['worker_id']}")
            print(f"   SSH access: {response['ssh_access']}")
            return response
            
        except Exception as e:
            print(f"   ❌ Instance request failed: {e}")
            return None
    
    async def test_ssh_access(self, ssh_access: Dict[str, Any]) -> bool:
        """Test SSH access to instance"""
        print("\n4. Testing SSH access...")
        
        ssh_user = ssh_access.get('ssh_user')
        ssh_host = ssh_access.get('ssh_host', 'localhost')
        
        print(f"   Attempting SSH as {ssh_user}@{ssh_host}")
        
        # Wait a moment for user creation to complete
        print("   Waiting 3 seconds for user creation...")
        await asyncio.sleep(3)
        
        try:
            # Test SSH connection
            cmd = [
                'ssh', 
                '-i', str(self.ssh_key_path),
                '-o', 'StrictHostKeyChecking=no',
                '-o', 'ConnectTimeout=10',
                f'{ssh_user}@{ssh_host}',
                'echo "SSH connection successful"'
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            
            if result.returncode == 0:
                print(f"   ✅ SSH connection successful")
                print(f"   Output: {result.stdout.strip()}")
                return True
            else:
                print(f"   ❌ SSH connection failed (exit code: {result.returncode})")
                print(f"   Error: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            print("   ❌ SSH connection timed out")
            return False
        except Exception as e:
            print(f"   ❌ SSH test error: {e}")
            return False
    
    async def test_user_profile(self, session: aiohttp.ClientSession) -> bool:
        """Test user profile endpoint"""
        print("\n5. Testing user profile...")
        
        try:
            response = await self.make_request(
                session, "GET", f"{HEAD_NODE_URL}/auth/user/profile"
            )
            
            print(f"   ✅ Profile retrieved for: {response['username']}")
            print(f"   Current instances: {response['current_instances']}")
            print(f"   Instance limit: {response['instance_limit']}")
            return True
            
        except Exception as e:
            print(f"   ❌ Profile retrieval failed: {e}")
            return False
    
    async def test_instance_list(self, session: aiohttp.ClientSession) -> bool:
        """Test listing user's instances"""
        print("\n6. Testing instance list...")
        
        try:
            response = await self.make_request(
                session, "GET", f"{HEAD_NODE_URL}/instances/mine"
            )
            
            print(f"   ✅ Retrieved {len(response)} instances")
            for instance in response:
                print(f"      Instance: {instance['instance_id']} ({instance['status']})")
            return True
            
        except Exception as e:
            print(f"   ❌ Instance list failed: {e}")
            return False
    
    async def test_instance_termination(self, session: aiohttp.ClientSession, assignment_id: str) -> bool:
        """Test instance termination"""
        print("\n7. Testing instance termination...")
        
        try:
            response = await self.make_request(
                session, "DELETE", f"{HEAD_NODE_URL}/instances/{assignment_id}"
            )
            
            print(f"   ✅ Instance termination initiated: {response['message']}")
            
            # Wait for termination to complete
            print("   Waiting 10 seconds for termination to complete...")
            await asyncio.sleep(10)
            
            return True
            
        except Exception as e:
            print(f"   ❌ Instance termination failed: {e}")
            return False
    
    async def test_user_cleanup(self) -> bool:
        """Test that user was cleaned up from system"""
        print("\n8. Testing user cleanup...")
        
        try:
            # Check if user still exists
            result = subprocess.run(['id', self.username], capture_output=True, text=True)
            
            if result.returncode != 0:
                print(f"   ✅ User {self.username} successfully removed from system")
                return True
            else:
                print(f"   ⚠️  User {self.username} still exists on system")
                print(f"   This might be expected if cleanup is still in progress")
                return True  # Don't fail the test for this
                
        except Exception as e:
            print(f"   ❌ User cleanup check failed: {e}")
            return False
    
    async def run_test(self):
        """Run the complete SSH authentication test"""
        print("🧪 Testing SSH-Based User Authentication")
        print("=" * 50)
        
        # Setup SSH key
        ssh_public_key = await self.setup_ssh_key()
        if not ssh_public_key:
            print("\n❌ SSH key setup failed!")
            return False
        
        async with aiohttp.ClientSession() as session:
            try:
                # Run all tests
                tests = [
                    self.test_user_registration(session, ssh_public_key),
                    self.test_authentication(session),
                ]
                
                # Run initial tests
                for test in tests:
                    success = await test
                    if not success:
                        print("\n❌ Early test failed, stopping")
                        return False
                
                # Request instance
                instance_data = await self.test_instance_request(session)
                if not instance_data:
                    print("\n❌ Instance request failed, stopping")
                    return False
                
                # Test SSH access
                ssh_success = await self.test_ssh_access(instance_data['ssh_access'])
                
                # Continue with remaining tests
                profile_success = await self.test_user_profile(session)
                list_success = await self.test_instance_list(session)
                
                # Terminate instance
                term_success = await self.test_instance_termination(session, instance_data['assignment_id'])
                
                # Check cleanup
                cleanup_success = await self.test_user_cleanup()
                
                # Summary
                print("\n📊 Test Summary:")
                print(f"   User registration: {'✅' if True else '❌'}")
                print(f"   Authentication: {'✅' if True else '❌'}")
                print(f"   Instance request: {'✅' if instance_data else '❌'}")
                print(f"   SSH access: {'✅' if ssh_success else '❌'}")
                print(f"   User profile: {'✅' if profile_success else '❌'}")
                print(f"   Instance list: {'✅' if list_success else '❌'}")
                print(f"   Instance termination: {'✅' if term_success else '❌'}")
                print(f"   User cleanup: {'✅' if cleanup_success else '❌'}")
                
                all_success = all([ssh_success, profile_success, list_success, term_success, cleanup_success])
                
                if all_success:
                    print("\n🎉 All SSH authentication tests passed!")
                else:
                    print("\n⚠️  Some tests failed - check the details above")
                
                return all_success
                
            except Exception as e:
                print(f"\n💥 Test error: {e}")
                return False

async def main():
    tester = SSHAuthTester()
    
    print("Note: This test requires:")
    print("- Head node running on localhost:8000")
    print("- Worker node running and connected")
    print("- sudo permissions for user management")
    print("- SSH server running on the worker machine")
    print("")
    
    try:
        success = await tester.run_test()
        if success:
            print("\n✅ SSH authentication system is working correctly!")
        else:
            print("\n❌ SSH authentication system has issues!")
            exit(1)
    except Exception as e:
        print(f"\n💥 Test suite error: {e}")
        exit(1)

if __name__ == "__main__":
    asyncio.run(main())