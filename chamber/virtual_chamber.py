"""
虛擬環境測試艙 (Virtual Chamber) 動力學物理模擬實現
"""

import time
import random
from datetime import datetime
from chamber.base import BaseChamber, ChamberState, ChamberTelemetry, STATE_METADATA


class VirtualChamber(BaseChamber):
    """虛擬環境試驗箱：包含熱力學升降溫、加除濕與安全開關模擬"""

    def __init__(self, ambient_temp: float = 25.0, ambient_humi: float = 55.0):
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

    def _shut_off_actuators(self):
        self.heater_active = False
        self.cooler_active = False
        self.humidifier_active = False
        self.dehumidifier_active = False

    def step(self, dt: float):
        """物理模擬步進 (秒)"""
        scaled_dt = dt * self.sim_speed

        if self.state == ChamberState.RUNNING:
            self.total_runtime_sec += scaled_dt

        # 箱門開啟：溫濕度迅速趨向室溫室濕
        if self.door_open:
            self.current_temp += (self.ambient_temp - self.current_temp) * min(1.0, 0.4 * scaled_dt)
            self.current_humi += (self.ambient_humi - self.current_humi) * min(1.0, 0.3 * scaled_dt)
            self._shut_off_actuators()
            return

        if self.state == ChamberState.RUNNING:
            # 溫度趨向目標值
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

            # 濕度趨向目標值
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
            # 關機/待機/警報狀態：自然回歸環境溫濕度
            self._shut_off_actuators()
            self.current_temp += (self.ambient_temp - self.current_temp) * min(1.0, 0.05 * scaled_dt)
            self.current_humi += (self.ambient_humi - self.current_humi) * min(1.0, 0.05 * scaled_dt)

        # 數值保護
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
            sim_speed=self.sim_speed
        )
