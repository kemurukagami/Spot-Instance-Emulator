import csv
import logging
from pathlib import Path
from typing import List, Dict, Optional
from sie.head_node.core.trace import TraceEvent, TraceAction, TraceSimulator, AvailableSpotInstance

logger = logging.getLogger(__name__)

class TraceParseError(Exception):
    """Exception raised when trace file parsing fails"""
    pass

class TraceParser:
    """Parser for CSV trace files"""

    @staticmethod
    def parse_trace_file(file_path: str, instance_type: str = "p3.8xlarge") -> TraceSimulator:
        """
        Parse a CSV trace file and return a TraceSimulator

        Args:
            file_path: Path to CSV file with format: timestamp_ms,action,node_id
            instance_type: Instance type to assign to all nodes in trace

        Returns:
            TraceSimulator with parsed events

        Raises:
            TraceParseError: If file format is invalid or file cannot be read
        """
        if not Path(file_path).exists():
            raise TraceParseError(f"Trace file not found: {file_path}")

        events = []
        node_ids_seen = set()

        try:
            with open(file_path, 'r') as f:
                reader = csv.reader(f)
                for line_num, row in enumerate(reader, 1):
                    try:
                        event = TraceParser._parse_trace_line(row, line_num)
                        events.append(event)
                        node_ids_seen.add(event.node_id)
                    except TraceParseError as e:
                        logger.error(f"Error parsing line {line_num}: {e}")
                        raise

        except IOError as e:
            raise TraceParseError(f"Failed to read trace file {file_path}: {e}")

        if not events:
            raise TraceParseError(f"No valid events found in trace file: {file_path}")

        # Sort events by timestamp for efficient playback
        events.sort()

        # Create simulator with parsed events and configured instance type
        simulator = TraceSimulator(events=events, default_instance_type=instance_type)

        logger.info(f"Parsed trace file: {file_path}")
        logger.info(f"  Events: {len(events)}")
        logger.info(f"  Unique nodes: {len(node_ids_seen)}")
        logger.info(f"  Time range: {events[0].timestamp_ms}ms - {events[-1].timestamp_ms}ms")
        logger.info(f"  Duration: {(events[-1].timestamp_ms - events[0].timestamp_ms) / 1000:.1f} seconds")

        return simulator

    @staticmethod
    def _parse_trace_line(row: List[str], line_num: int) -> TraceEvent:
        """
        Parse a single line from the trace CSV

        Expected format: timestamp_ms,action,node_id
        """
        if len(row) != 3:
            raise TraceParseError(f"Line {line_num}: Expected 3 columns, got {len(row)}")

        timestamp_str, action_str, node_id = [col.strip() for col in row]

        # Parse timestamp
        try:
            timestamp_ms = int(timestamp_str)
            if timestamp_ms < 0:
                raise TraceParseError(f"Line {line_num}: Timestamp cannot be negative: {timestamp_ms}")
        except ValueError:
            raise TraceParseError(f"Line {line_num}: Invalid timestamp: '{timestamp_str}'")

        # Parse action
        try:
            action = TraceAction(action_str.lower())
        except ValueError:
            raise TraceParseError(f"Line {line_num}: Invalid action '{action_str}', expected 'add' or 'remove'")

        # Validate node_id
        if not node_id:
            raise TraceParseError(f"Line {line_num}: Node ID cannot be empty")

        return TraceEvent(
            timestamp_ms=timestamp_ms,
            action=action,
            node_id=node_id
        )

    @staticmethod
    def validate_trace(simulator: TraceSimulator) -> List[str]:
        """
        Validate trace for common issues

        Returns:
            List of warning messages (empty if no issues)
        """
        warnings = []
        node_states = {}  # node_id -> is_available

        for event in simulator.events:
            current_state = node_states.get(event.node_id, False)

            if event.action == TraceAction.ADD:
                if current_state:
                    warnings.append(f"Node {event.node_id} added while already available at {event.timestamp_ms}ms")
                node_states[event.node_id] = True

            elif event.action == TraceAction.REMOVE:
                if not current_state:
                    warnings.append(f"Node {event.node_id} removed while not available at {event.timestamp_ms}ms")
                node_states[event.node_id] = False

        # Check for duplicate timestamps
        timestamps = [event.timestamp_ms for event in simulator.events]
        if len(timestamps) != len(set(timestamps)):
            warnings.append("Trace contains duplicate timestamps")

        return warnings

def parse_instance_type_from_filename(file_path: str) -> str:
    """
    Extract instance type from trace filename

    Examples:
        "p3-trace.csv" -> "p3.xlarge"
        "g4dn-trace.csv" -> "g4dn.xlarge"
        "other-trace.csv" -> "unknown"
    """
    filename = Path(file_path).stem

    # Common instance type patterns
    if filename.startswith("p3"):
        return "p3.8xlarge"  # Default to 4-GPU configuration
    elif filename.startswith("g4dn"):
        return "g4dn.xlarge"
    elif filename.startswith("c5"):
        return "c5.xlarge"
    elif filename.startswith("m5"):
        return "m5.xlarge"
    else:
        return "unknown"