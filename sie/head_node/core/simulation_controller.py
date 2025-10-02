import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, Callable, List
from sie.head_node.core.trace import TraceSimulator, TraceEvent, TraceAction
from sie.head_node.core.pool_manager import PoolManager
from sie.head_node.core.trace_parser import parse_instance_type_from_filename
from sie.common.messages import InterruptMessage, UnassignInstanceMessage

logger = logging.getLogger(__name__)

class SimulationController:
    """Controls trace playback and manages simulation timing"""

    def __init__(self, pool_manager: PoolManager, trace_simulator: TraceSimulator, connection_manager=None):
        self.pool_manager = pool_manager
        self.trace_simulator = trace_simulator
        self.connection_manager = connection_manager  # For sending interruption warnings
        self.simulation_task: Optional[asyncio.Task] = None
        self.is_running = False

        # Callbacks for external notifications
        self.on_spot_instance_added: Optional[Callable[[str, str], None]] = None
        self.on_spot_instance_removed: Optional[Callable[[str, str], None]] = None

        # Set trace simulator in pool manager
        self.pool_manager.set_trace_simulator(trace_simulator)

        # Current event index for efficient processing
        self._current_event_index = 0

    async def start_simulation(self) -> None:
        """Start the simulation playback"""
        if self.is_running:
            logger.warning("Simulation is already running")
            return

        if not self.trace_simulator.events:
            logger.warning("No trace events to simulate")
            return

        self.is_running = True
        self.trace_simulator.start_time = datetime.utcnow()
        self.trace_simulator.current_time_ms = 0
        self._current_event_index = 0

        logger.info(f"Starting trace simulation with {len(self.trace_simulator.events)} events")
        logger.info(f"Simulation speed: {self.trace_simulator.simulation_speed}x")
        logger.info(f"First event at: {self.trace_simulator.events[0].timestamp_ms}ms")
        logger.info(f"Last event at: {self.trace_simulator.events[-1].timestamp_ms}ms")

        # Start simulation task
        self.simulation_task = asyncio.create_task(self._simulation_loop())

    async def stop_simulation(self) -> None:
        """Stop the simulation playback"""
        if not self.is_running:
            return

        self.is_running = False
        if self.simulation_task:
            self.simulation_task.cancel()
            try:
                await self.simulation_task
            except asyncio.CancelledError:
                pass

        logger.info("Stopped trace simulation")

    async def pause_simulation(self) -> None:
        """Pause the simulation"""
        self.trace_simulator.is_paused = True
        logger.info("Paused trace simulation")

    async def resume_simulation(self) -> None:
        """Resume the simulation"""
        self.trace_simulator.is_paused = False
        logger.info("Resumed trace simulation")

    async def seek_to_time(self, time_ms: int) -> None:
        """
        Seek to a specific time in the trace

        Args:
            time_ms: Target time in milliseconds from trace start
        """
        if time_ms < 0:
            time_ms = 0

        # Find the appropriate event index
        target_index = 0
        for i, event in enumerate(self.trace_simulator.events):
            if event.timestamp_ms <= time_ms:
                target_index = i + 1
            else:
                break

        # Reset simulation state
        self.trace_simulator.available_spot_instances.clear()
        self.trace_simulator.current_time_ms = time_ms
        self._current_event_index = target_index

        # Replay events up to target time
        for i in range(target_index):
            event = self.trace_simulator.events[i]
            await self._process_event(event)

        logger.info(f"Seeked to time {time_ms}ms (event index {target_index})")

    def set_simulation_speed(self, speed: float) -> None:
        """Set simulation speed multiplier"""
        if speed <= 0:
            raise ValueError("Simulation speed must be positive")

        self.trace_simulator.simulation_speed = speed
        logger.info(f"Set simulation speed to {speed}x")

    async def _simulation_loop(self) -> None:
        """Main simulation loop that processes trace events"""
        try:
            while self.is_running and self._current_event_index < len(self.trace_simulator.events):
                if self.trace_simulator.is_paused:
                    await asyncio.sleep(0.1)
                    continue

                # Get next event
                next_event = self.trace_simulator.events[self._current_event_index]

                # Calculate how long to wait for this event
                target_time_ms = next_event.timestamp_ms
                current_simulation_time = self._get_current_simulation_time_ms()

                if target_time_ms > current_simulation_time:
                    wait_time_ms = target_time_ms - current_simulation_time
                    wait_time_real = wait_time_ms / (1000.0 * self.trace_simulator.simulation_speed)

                    if wait_time_real > 0:
                        await asyncio.sleep(wait_time_real)

                # Process the event
                await self._process_event(next_event)
                self.trace_simulator.current_time_ms = target_time_ms
                self._current_event_index += 1

            if self.is_running:
                logger.info("Simulation completed - all events processed")
                self.is_running = False

        except asyncio.CancelledError:
            logger.info("Simulation loop cancelled")
            raise
        except Exception as e:
            logger.error(f"Simulation loop error: {e}")
            self.is_running = False
            raise

    async def _process_event(self, event: TraceEvent) -> None:
        """Process a single trace event"""
        try:
            if event.action == TraceAction.ADD:
                await self._handle_add_event(event)
            elif event.action == TraceAction.REMOVE:
                await self._handle_remove_event(event)
            else:
                logger.warning(f"Unknown trace action: {event.action}")

        except Exception as e:
            logger.error(f"Error processing event {event}: {e}")

    async def _handle_add_event(self, event: TraceEvent) -> None:
        """Handle ADD event - make spot instance available"""
        instance_type = self._infer_instance_type(event.node_id)
        self.pool_manager.add_spot_instance(event.node_id, instance_type)

        # Notify external listeners
        if self.on_spot_instance_added:
            try:
                await self.on_spot_instance_added(event.node_id, instance_type)
            except Exception as e:
                logger.error(f"Error in spot instance added callback: {e}")

    async def _handle_remove_event(self, event: TraceEvent) -> None:
        """Handle REMOVE event - send 2-min warning, then unassign after grace period"""
        # Check if this spot instance is assigned to a worker
        spot_instance = self.pool_manager.trace_simulator.available_spot_instances.get(event.node_id)

        if spot_instance and spot_instance.is_assigned:
            worker_id = spot_instance.assigned_worker_id
            instance = self.pool_manager.get_instance_for_worker(worker_id)

            if instance and self.connection_manager:
                # Send 2-minute interruption warning
                grace_period_sim = 120  # 2 minutes in simulation time
                grace_period_real = grace_period_sim / self.trace_simulator.simulation_speed

                logger.info(f"Sending spot termination warning for {event.node_id} to worker {worker_id} (grace: {grace_period_real:.1f}s real / {grace_period_sim}s sim)")
                msg = InterruptMessage(
                    instance_id=instance.instance_id,
                    warning_time=grace_period_sim,
                    simulation_speed=self.trace_simulator.simulation_speed
                )
                await self.connection_manager.send_to_worker(worker_id, msg.dict())

                # Update worker state to INTERRUPTED
                self.pool_manager.mark_for_interruption(instance.instance_id, warning_time=grace_period_sim)

                # Schedule unassignment after grace period (simulation-adjusted)
                asyncio.create_task(self._delayed_unassignment(event.node_id, worker_id, instance.instance_id, grace_period_sim))
                logger.info(f"Worker {worker_id} has {grace_period_real:.1f}s real-time ({grace_period_sim}s sim-time) to clean up")
                return  # Don't remove spot instance yet

        # Remove spot instance from pool if not assigned
        unassigned_worker = self.pool_manager.remove_spot_instance(event.node_id)

        # Notify external listeners (for visualization)
        if self.on_spot_instance_removed:
            try:
                await self.on_spot_instance_removed(event.node_id, unassigned_worker)
            except Exception as e:
                logger.error(f"Error in spot instance removed callback: {e}")

    async def _delayed_unassignment(self, spot_instance_id: str, worker_id: str, instance_id: str, delay: int) -> None:
        """Unassign worker after grace period (adjusted for simulation speed)"""
        # Adjust delay for simulation speed: real_time = sim_time / speed
        real_delay = delay / self.trace_simulator.simulation_speed
        logger.info(f"Waiting {real_delay:.1f}s real-time ({delay}s sim-time at {self.trace_simulator.simulation_speed}x speed)")

        await asyncio.sleep(real_delay)

        logger.info(f"Grace period ended, unassigning worker {worker_id} from spot instance {spot_instance_id}")

        # Send unassignment message to worker
        if self.connection_manager:
            msg = UnassignInstanceMessage(instance_id=instance_id, worker_id=worker_id)
            await self.connection_manager.send_to_worker(worker_id, msg.dict())

        # Remove spot instance from pool
        self.pool_manager.remove_spot_instance(spot_instance_id)

        # Notify visualization
        if self.on_spot_instance_removed:
            try:
                await self.on_spot_instance_removed(spot_instance_id, worker_id)
            except Exception as e:
                logger.error(f"Error in spot instance removed callback: {e}")

    def _get_current_simulation_time_ms(self) -> int:
        """Calculate current simulation time based on real time elapsed"""
        if not self.trace_simulator.start_time:
            return 0

        real_elapsed = (datetime.utcnow() - self.trace_simulator.start_time).total_seconds()
        sim_elapsed_ms = real_elapsed * 1000 * self.trace_simulator.simulation_speed
        return int(sim_elapsed_ms)

    def _infer_instance_type(self, node_id: str) -> str:
        """
        Infer instance type from node ID
        This is a simple implementation - could be enhanced with mapping files
        """
        # Try to extract from node ID pattern
        if 'p3' in node_id.lower():
            return 'p3.xlarge'
        elif 'g4dn' in node_id.lower():
            return 'g4dn.xlarge'
        elif 'c5' in node_id.lower():
            return 'c5.xlarge'
        elif 'm5' in node_id.lower():
            return 'm5.xlarge'
        else:
            # Default based on some heuristic or configuration
            return 'p3.xlarge'

    def get_simulation_status(self) -> dict:
        """Get current simulation status"""
        if not self.is_running and self._current_event_index == 0:
            status = "stopped"
        elif self.trace_simulator.is_paused:
            status = "paused"
        elif self.is_running:
            status = "running"
        else:
            status = "completed"

        total_events = len(self.trace_simulator.events)
        progress = (self._current_event_index / total_events * 100) if total_events > 0 else 0

        # Get max time from last event
        max_time_ms = 0
        if self.trace_simulator.events:
            max_time_ms = self.trace_simulator.events[-1].timestamp_ms

        # Update current time to real simulation time (for display between events)
        if self.is_running and not self.trace_simulator.is_paused:
            current_simulation_time = self._get_current_simulation_time_ms()
            # Only update if we're past the stored time (prevents going backwards)
            if current_simulation_time > self.trace_simulator.current_time_ms:
                self.trace_simulator.current_time_ms = current_simulation_time

        return {
            "status": status,
            "current_time_ms": self.trace_simulator.current_time_ms,
            "max_time_ms": max_time_ms,
            "simulation_speed": self.trace_simulator.simulation_speed,
            "events_processed": self._current_event_index,
            "total_events": total_events,
            "progress_percent": round(progress, 2),
            "available_spot_instances": len(self.pool_manager.get_available_spot_instances()),
            "assigned_spot_instances": len(self.pool_manager.get_assigned_spot_instances())
        }

    def get_upcoming_events(self, count: int = 10) -> List[TraceEvent]:
        """Get the next few events in the trace"""
        start_index = self._current_event_index
        end_index = min(start_index + count, len(self.trace_simulator.events))
        return self.trace_simulator.events[start_index:end_index]