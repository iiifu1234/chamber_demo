"""
Virtual Chamber Dynamics & Test Profile/Schedule Simulation
"""

import time
import random
from datetime import datetime, timedelta
from typing import List, Dict, Any
from chamber.base import BaseChamber, ChamberState, ChamberTelemetry, STATE_METADATA


class VirtualChamber(BaseChamber):
    """Virtual Environmental Test Chamber with Thermodynamic & Schedule Simulation"""

    def __init__(
        self,
        ambient_temp: float = 25.0,
        ambient_humi: float = 55.0,
        test_name: str = "Molex Standard Testing",
        test_operator: str = "Reliability Lab",
        test_total_hours: float = 8.0,
        test_elapsed_hours: float = 3.5,
        default_bookings: List[Dict[str, Any]] = None
    ):
        self.ambient_temp = ambient_temp
        self.ambient_humi = ambient_humi

        self.state = ChamberState.OFF
        self.current_temp = ambient_temp
        self.current_humi = ambient_humi
        self.target_temp = 60.0
        self.target_humi = 75.0

        self.door_open = False
        self.sim_speed = 1.0

        self.heater_active = False
        self.cooler_active = False
        self.humidifier_active = False
        self.dehumidifier_active = False

        self.total_runtime_sec = 0.0
        self.last_update_time = time.time()
        self._connected = True

        # Test Execution Tracking
        self.test_name = test_name
        self.test_operator = test_operator
        self.test_total_sec = test_total_hours * 3600.0
        self.test_elapsed_sec = test_elapsed_hours * 3600.0

        # Booking / Reservation Schedule
        self.bookings: List[Dict[str, Any]] = default_bookings or []

    def connect(self) -> bool:
        self._connected = True
        return True

    def disconnect(self):
        self._connected = False

    def set_power(self, on: bool):
        if on:
            if self.state == ChamberState.OFF:
                self.state = ChamberState.STANDBY
        else:
            self.state = ChamberState.OFF
            self._shut_off_actuators()

    def set_run_state(self, run: bool):
        if run:
            if self.state in (ChamberState.STANDBY, ChamberState.ALARM):
                self.state = ChamberState.RUNNING
        else:
            if self.state == ChamberState.RUNNING:
                self.state = ChamberState.STANDBY
                self._shut_off_actuators()

    def set_target_temperature(self, temp: float):
        self.target_temp = max(-50.0, min(180.0, temp))

    def set_target_humidity(self, humi: float):
        self.target_humi = max(10.0, min(98.0, humi))

    def set_sim_speed(self, speed: float):
        self.sim_speed = max(0.1, min(20.0, speed))

    def toggle_door(self) -> bool:
        self.door_open = not self.door_open
        if self.door_open:
            self._shut_off_actuators()
        return self.door_open

    def trigger_alarm(self):
        self.state = ChamberState.ALARM
        self._shut_off_actuators()

    def reset_alarm(self):
        if self.state == ChamberState.ALARM:
            self.state = ChamberState.STANDBY

    def set_test_profile(self, name: str, operator: str, total_hours: float):
        self.test_name = name
        self.test_operator = operator
        self.test_total_sec = max(60.0, total_hours * 3600.0)
        self.test_elapsed_sec = 0.0

    def add_booking(self, project: str, engineer: str, start_time: str, duration: str):
        self.bookings.append({
            "project": project,
            "engineer": engineer,
            "start_time": start_time,
            "duration": duration,
            "status": "Confirmed"
        })

    def _shut_off_actuators(self):
        self.heater_active = False
        self.cooler_active = False
        self.humidifier_active = False
        self.dehumidifier_active = False

    def step(self, dt: float):
        scaled_dt = dt * self.sim_speed

        if self.state == ChamberState.RUNNING:
            self.total_runtime_sec += scaled_dt
            self.test_elapsed_sec += scaled_dt

            # Loop or clamp test elapsed
            if self.test_elapsed_sec >= self.test_total_sec:
                self.test_elapsed_sec = self.test_total_sec

        if self.door_open:
            self.current_temp += (self.ambient_temp - self.current_temp) * min(1.0, 0.4 * scaled_dt)
            self.current_humi += (self.ambient_humi - self.current_humi) * min(1.0, 0.3 * scaled_dt)
            self._shut_off_actuators()
            return

        if self.state == ChamberState.RUNNING:
            temp_diff = self.target_temp - self.current_temp
            if abs(temp_diff) > 0.15:
                rate = 1.8 if temp_diff > 0 else 1.4
                self.heater_active = temp_diff > 0
                self.cooler_active = temp_diff < 0
                step_val = rate * scaled_dt * (1.0 if temp_diff > 0 else -1.0)
                if abs(step_val) > abs(temp_diff):
                    self.current_temp = self.target_temp
                else:
                    self.current_temp += step_val
            else:
                self.heater_active = False
                self.cooler_active = False
                self.current_temp += random.uniform(-0.05, 0.05)

            humi_diff = self.target_humi - self.current_humi
            if abs(humi_diff) > 0.3:
                h_rate = 2.2 if humi_diff > 0 else 1.8
                self.humidifier_active = humi_diff > 0
                self.dehumidifier_active = humi_diff < 0
                h_step = h_rate * scaled_dt * (1.0 if humi_diff > 0 else -1.0)
                if abs(h_step) > abs(humi_diff):
                    self.current_humi = self.target_humi
                else:
                    self.current_humi += h_step
            else:
                self.humidifier_active = False
                self.dehumidifier_active = False
                self.current_humi += random.uniform(-0.12, 0.12)

        elif self.state in (ChamberState.OFF, ChamberState.STANDBY, ChamberState.ALARM):
            self._shut_off_actuators()
            self.current_temp += (self.ambient_temp - self.current_temp) * min(1.0, 0.05 * scaled_dt)
            self.current_humi += (self.ambient_humi - self.current_humi) * min(1.0, 0.05 * scaled_dt)

        self.current_temp = max(-50.0, min(180.0, self.current_temp))
        self.current_humi = max(5.0, min(99.0, self.current_humi))

    def get_telemetry(self) -> ChamberTelemetry:
        now = time.time()
        dt = now - self.last_update_time
        self.last_update_time = now
        self.step(dt)

        st_text, st_color = STATE_METADATA[self.state]
        sec = int(self.total_runtime_sec)
        uptime_str = f"{sec // 3600:02d}:{(sec % 3600) // 60:02d}:{sec % 60:02d}"

        # Calculate Remaining Time & Completion Time
        remaining_sec = max(0.0, self.test_total_sec - self.test_elapsed_sec)
        rem_h = int(remaining_sec // 3600)
        rem_m = int((remaining_sec % 3600) // 60)
        rem_s = int(remaining_sec % 60)
        test_remaining_str = f"{rem_h:02d}h {rem_m:02d}m {rem_s:02d}s"

        progress_pct = round(min(100.0, (self.test_elapsed_sec / max(1.0, self.test_total_sec)) * 100), 1)

        # Estimated Completion Timestamp
        est_end_dt = datetime.now() + timedelta(seconds=remaining_sec)
        est_completion_time = est_end_dt.strftime("%Y-%m-%d %H:%M")

        # Next Available Slot Calculation
        if self.state in (ChamberState.OFF, ChamberState.STANDBY):
            next_available_slot = "Available Immediately"
        else:
            next_available_slot = f"Available after {est_end_dt.strftime('%H:%M Today') if est_end_dt.date() == datetime.now().date() else est_end_dt.strftime('%m/%d %H:%M')}"

        return ChamberTelemetry(
            timestamp=datetime.now().strftime("%H:%M:%S"),
            temp_pv=round(self.current_temp, 2),
            temp_sv=round(self.target_temp, 2),
            humi_pv=round(self.current_humi, 2),
            humi_sv=round(self.target_humi, 2),
            state=self.state,
            state_text=st_text,
            state_color=st_color,
            heater=self.heater_active,
            cooler=self.cooler_active,
            humidifier=self.humidifier_active,
            dehumidifier=self.dehumidifier_active,
            door_open=self.door_open,
            uptime_sec=self.total_runtime_sec,
            uptime_str=uptime_str,
            sim_speed=self.sim_speed,
            test_name=self.test_name,
            test_operator=self.test_operator,
            test_total_sec=self.test_total_sec,
            test_remaining_sec=remaining_sec,
            test_remaining_str=test_remaining_str,
            test_progress_pct=progress_pct,
            est_completion_time=est_completion_time,
            next_available_slot=next_available_slot,
            bookings=list(self.bookings)
        )
