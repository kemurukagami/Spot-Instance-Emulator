# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a **Spot Instance Emulator** that simulates AWS EC2 Spot Instance behavior for testing application resilience to spot interruptions. The system uses WebSocket-based real-time communication between a head node (supervisor) and multiple instance nodes (simulated spot instances).

## Architecture

- **Head Node** (`sie/head_node/`): Central supervisor managing instance pool, WebSocket server, admin API
- **Instance Nodes** (`sie/instance_node/`): Worker nodes simulating individual spot instances with hardware detection
- **Common** (`sie/common/`): Shared message protocols, constants, and Pydantic models

Communication flow: Instance nodes connect via WebSocket to head node, send heartbeats, receive interruption commands, and notify user applications via webhook.

## Development Commands

### Running the System
```bash
# Start head node (port 8000)
python run_head.py

# Start instance nodes (different ports)
python run_instance.py --port 8001 --instance-id i-node1
python run_instance.py --port 8002 --instance-type m5.large

# Trigger manual interruption for testing
python test_interruption.py --list
python test_interruption.py --instance-id <id> --warning-time 30
```

### Testing
```bash
# Run all tests
python run_tests.py

# Run specific module tests
python run_tests.py --module common
python run_tests.py --module head
python run_tests.py --module instance

# Run with coverage report
python run_tests.py --coverage
```

### API Access
- Admin API: `http://localhost:8000/admin/instances` (list instances)
- Interactive docs: `http://localhost:8000/docs` (Swagger UI)
- Instance status: `http://localhost:8001/instance/status`

## Key Implementation Details

### JSON Serialization
All WebSocket messages use `json.dumps(message, default=str)` to handle Pydantic datetime objects. The head node uses `websocket.send_text(json_str)` instead of `send_json()` for proper datetime handling.

### Message Protocol
Messages follow Pydantic models in `sie/common/messages.py`:
- REGISTER: Instance → Head (hardware profile, auto-registration)
- HEARTBEAT: Instance → Head (every 30s, health monitoring)
- INTERRUPT: Head → Instance (spot interruption with warning time)
- ACKNOWLEDGE: Bidirectional (message confirmation)

### Instance Lifecycle
1. Instance starts, detects hardware via `psutil`
2. Connects to head node WebSocket (`ws://localhost:8000/ws`)
3. Sends REGISTER message with hardware profile
4. Maintains heartbeat every 30 seconds
5. On interruption: receives warning, notifies user webhook, terminates after warning period
6. Process completely terminates with `os._exit(0)` to simulate spot instance behavior

### Webhook System
Instance nodes can notify user applications of impending termination:
```bash
# Configure webhook
curl -X POST http://localhost:8001/webhook/configure \
  -H "Content-Type: application/json" \
  -d '{"url": "http://app:3000/spot-interrupt", "enabled": true}'
```

### Testing Patterns
- Use `AsyncMock` for WebSocket mocking
- JSON datetime serialization requires `default=str` parameter
- Tests use `asyncio.run()` wrapper pattern for async methods
- Mock hardware detection with `patch('psutil.cpu_count')`

### Current Status
Phase 1 (Core Infrastructure) is complete with full test coverage. Pending phases include spot market dynamics and advanced features. All 98+ unit tests pass.