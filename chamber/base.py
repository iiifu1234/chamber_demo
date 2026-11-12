"""
Chamber Base Interface & Data Models
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Dict, Tuple, List, Any


class ChamberState(IntEnum):
    OFF = 0       # Power Off
    STANDBY = 1   # Standby
    RUNNING = 2   # Running
    ALARM = 3     # Alarm / Fault


STATE_METADATA: Dict[ChamberState, Tuple[str, str]] = {
    ChamberState.OFF: ("OFF", "#6c757d"),
    ChamberState.STANDBY: ("STANDBY", "#ffc107"),
    ChamberState.RUNNING: ("RUNNING", "#28a745"),
    ChamberState.ALARM: ("ALARM", "#dc3545"),
}


@dataclass
class ChamberTelemetry:
    """Real-time Telemetry Data Model"""
    timestamp: str
    temp_pv: float
    temp_sv: float
    humi_pv: float
    humi_sv: float
    state: ChamberState
    state_text: str
    state_color: str
    heater: bool
    cooler: bool
    humidifier: bool
    dehumidifier: bool
    door_open: bool
    uptime_sec: float
    uptime_str: str
    sim_speed: float

    # Test Execution & Schedule Metadata
    test_name: str = "Standard Idle"
    test_operator: str = "Unassigned"
    test_total_sec: float = 0.0
    test_remaining_sec: float = 0.0
    test_remaining_str: str = "--:--:--"
    test_progress_pct: float = 0.0
    est_completion_time: str = "N/A"
    next_available_slot: str = "Available Now"
    bookings: List[Dict[str, Any]] = field(default_factory=list)

    def to_api_dict(self) -> Dict[str, Any]:
        """Serialize telemetry to standard API JSON dictionary"""
        return {
            "time": self.timestamp,
            "temp_pv": self.temp_pv,
            "temp_sv": self.temp_sv,
            "humi_pv": self.humi_pv,
            "humi_sv": self.humi_sv,
            "state": int(self.state),
            "state_text": self.state_text,
            "state_color": self.state_color,
            "heater": self.heater,
            "cooler": self.cooler,
            "humidifier": self.humidifier,
            "dehumidifier": self.dehumidifier,
            "door_open": self.door_open,
            "uptime_sec": self.uptime_sec,
            "uptime": self.uptime_str,
            "sim_speed": self.sim_speed,
            "test_name": self.test_name,
            "test_operator": self.test_operator,
            "test_total_sec": self.test_total_sec,
            "test_remaining_sec": self.test_remaining_sec,
            "test_remaining_str": self.test_remaining_str,
            "test_progress_pct": self.test_progress_pct,
            "est_completion_time": self.est_completion_time,
            "next_available_slot": self.next_available_slot,
            "bookings": self.bookings,
        }



class BaseChamber(ABC):
    """Abstract Test Chamber Device Interface"""

    @abstractmethod
    def connect(self) -> bool:
        """Connect to device"""
        pass

    @abstractmethod
    def disconnect(self):
        """Disconnect device"""
        pass

    @abstractmethod
    def get_telemetry(self) -> ChamberTelemetry:
        """Retrieve real-time telemetry"""
        pass

    @abstractmethod
    def set_power(self, on: bool):
        """Toggle main power"""
        pass

    @abstractmethod
    def set_run_state(self, run: bool):
        """Start / Pause operation"""
        pass

    @abstractmethod
    def set_target_temperature(self, temp: float):
        """Set target temperature (SV)"""
        pass

    @abstractmethod
    def set_target_humidity(self, humi: float):
        """Set target humidity (SV)"""
        pass

    @abstractmethod
    def toggle_door(self) -> bool:
        """Open / Close door"""
        pass

    @abstractmethod
    def trigger_alarm(self):
        """Trigger safety alarm"""
        pass

    @abstractmethod
    def reset_alarm(self):
        """Reset alarm"""
        pass
