"""
Chamber Controller with Multi-Chamber Support & Schedule / Booking Management
"""

import time
import logging
from typing import Dict, Optional, List, Any
from chamber.base import BaseChamber, ChamberTelemetry, ChamberState
from chamber.virtual_chamber import VirtualChamber
from commands.base import (
    ICommand, PowerCommand, RunCommand, SetTargetCommand,
    DoorCommand, AlarmCommand
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


class ChamberController:
    """Multi-Chamber Dispatcher & Test Schedule Manager"""

    def __init__(self, chambers: Optional[Dict[str, BaseChamber]] = None):
        if chambers:
            self.chambers = chambers
        else:
            # Chamber 1: High-Temp / Humidity Aging
            c1 = VirtualChamber(
                ambient_temp=25.0,
                ambient_humi=55.0,
                test_name="Molex Gen5 Micro-Fit 85°C/85%RH Reliability Test #REL-2026-088",
                test_operator="Patrick Chen",
                test_total_hours=12.0,
                test_elapsed_hours=7.5,
                default_bookings=[
                    {"project": "Molex Quad-Row Connector Thermal Life", "engineer": "Kevin Lin", "start_time": "Today 21:00", "duration": "10h", "status": "Confirmed"},
                    {"project": "Automotive Power Pin Aging Validation", "engineer": "Sarah Lee", "start_time": "Tomorrow 08:30", "duration": "24h", "status": "Scheduled"}
                ]
            )
            c1.state = ChamberState.RUNNING
            c1.target_temp = 85.0
            c1.target_humi = 85.0
            c1.current_temp = 84.8
            c1.current_humi = 85.2

            # Chamber 2: Cryogenic Shock
            c2 = VirtualChamber(
                ambient_temp=22.0,
                ambient_humi=50.0,
                test_name="Mil-Std Thermal Shock Cycling (-40°C ~ +125°C) #TS-104B",
                test_operator="David Chang",
                test_total_hours=6.0,
                test_elapsed_hours=4.2,
                default_bookings=[
                    {"project": "High-Speed I/O Harsh Environment Shock", "engineer": "Patrick Chen", "start_time": "Today 19:30", "duration": "6h", "status": "Confirmed"},
                    {"project": "Flexible Circuit Low-Temp Bend Test", "engineer": "Jason Huang", "start_time": "Tomorrow 14:00", "duration": "8h", "status": "Scheduled"}
                ]
            )
            c2.state = ChamberState.RUNNING
            c2.target_temp = -20.0
            c2.target_humi = 25.0
            c2.current_temp = -19.5
            c2.current_humi = 25.4

            # Chamber 3: Standard Environmental Chamber
            c3 = VirtualChamber(
                ambient_temp=24.0,
                ambient_humi=60.0,
                test_name="Molex SMT Environmental Moisture Resistance Test #ENV-03",
                test_operator="Reliability Lab",
                test_total_hours=24.0,
                test_elapsed_hours=18.0,
                default_bookings=[
                    {"project": "Next-Gen Board-to-Board Validation", "engineer": "Eric Wang", "start_time": "Tomorrow 10:00", "duration": "12h", "status": "Confirmed"}
                ]
            )
            c3.state = ChamberState.RUNNING
            c3.target_temp = 40.0
            c3.target_humi = 60.0
            c3.current_temp = 40.1
            c3.current_humi = 59.8

            self.chambers: Dict[str, BaseChamber] = {
                "chamber-1": c1,
                "chamber-2": c2,
                "chamber-3": c3,
            }

        self.command_history: List[str] = []

    def get_chamber(self, chamber_id: str = "chamber-1") -> BaseChamber:
        return self.chambers.get(chamber_id, next(iter(self.chambers.values())))

    def dispatch(self, chamber_id: str, command: ICommand):
        ch = self.get_chamber(chamber_id)
        ts = time.strftime("%H:%M:%S")
        log_entry = f"[{ts}] [{chamber_id}] Command -> {command.name}"
        logging.info(log_entry)
        self.command_history.append(log_entry)
        return command.execute(ch)

    def power(self, on: bool, chamber_id: str = "chamber-1"):
        return self.dispatch(chamber_id, PowerCommand(on))

    def run(self, start: bool, chamber_id: str = "chamber-1"):
        return self.dispatch(chamber_id, RunCommand(start))

    def set_target(self, temp: Optional[float] = None, humi: Optional[float] = None, chamber_id: str = "chamber-1"):
        return self.dispatch(chamber_id, SetTargetCommand(temp=temp, humi=humi))

    def toggle_door(self, chamber_id: str = "chamber-1"):
        return self.dispatch(chamber_id, DoorCommand())

    def alarm(self, trigger: bool = True, chamber_id: str = "chamber-1"):
        return self.dispatch(chamber_id, AlarmCommand(trigger))

    def set_speed(self, speed: float, chamber_id: str = "chamber-1"):
        ch = self.get_chamber(chamber_id)
        if hasattr(ch, "set_sim_speed"):
            ch.set_sim_speed(speed)

    def add_booking(self, chamber_id: str, project: str, engineer: str, start_time: str, duration: str):
        ch = self.get_chamber(chamber_id)
        if hasattr(ch, "add_booking"):
            ch.add_booking(project=project, engineer=engineer, start_time=start_time, duration=duration)

    def set_test_profile(self, chamber_id: str, name: str, operator: str, total_hours: float):
        ch = self.get_chamber(chamber_id)
        if hasattr(ch, "set_test_profile"):
            ch.set_test_profile(name=name, operator=operator, total_hours=total_hours)

    def get_telemetry(self, chamber_id: str = "chamber-1") -> ChamberTelemetry:
        return self.get_chamber(chamber_id).get_telemetry()

    def get_all_telemetry(self) -> Dict[str, ChamberTelemetry]:
        return {cid: ch.get_telemetry() for cid, ch in self.chambers.items()}
