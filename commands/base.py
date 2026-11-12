"""
命令設計模式 (Command Pattern) 基礎定義
將對機台的操作封裝為可追溯、可非同步執行、可重播的 Command 物件
"""

from abc import ABC, abstractmethod
from typing import Any, Optional
from chamber.base import BaseChamber


class ICommand(ABC):
    """抽象命令介面"""

    @property
    @abstractmethod
    def name(self) -> str:
        """命令名稱"""
        pass

    @abstractmethod
    def execute(self, chamber: BaseChamber) -> Any:
        """執行命令"""
        pass


class PowerCommand(ICommand):
    """主電源控制命令"""
    def __init__(self, on: bool):
        self.on = on

    @property
    def name(self) -> str:
        return f"Power({'ON' if self.on else 'OFF'})"

    def execute(self, chamber: BaseChamber) -> bool:
        chamber.set_power(self.on)
        return self.on


class RunCommand(ICommand):
    """運轉/暫停命令"""
    def __init__(self, run: bool):
        self.run = run

    @property
    def name(self) -> str:
        return f"Run({'START' if self.run else 'PAUSE'})"

    def execute(self, chamber: BaseChamber) -> bool:
        chamber.set_run_state(self.run)
        return self.run


class SetTargetCommand(ICommand):
    """設定目標溫濕度命令"""
    def __init__(self, temp: Optional[float] = None, humi: Optional[float] = None):
        self.temp = temp
        self.humi = humi

    @property
    def name(self) -> str:
        return f"SetTarget(temp={self.temp}, humi={self.humi})"

    def execute(self, chamber: BaseChamber) -> dict:
        results = {}
        if self.temp is not None:
            chamber.set_target_temperature(self.temp)
            results["temp"] = self.temp
        if self.humi is not None:
            chamber.set_target_humidity(self.humi)
            results["humi"] = self.humi
        return results


class DoorCommand(ICommand):
    """艙門開關命令"""
    @property
    def name(self) -> str:
        return "ToggleDoor"

    def execute(self, chamber: BaseChamber) -> bool:
        return chamber.toggle_door()


class AlarmCommand(ICommand):
    """警報觸發與復歸命令"""
    def __init__(self, trigger: bool = True):
        self.trigger = trigger

    @property
    def name(self) -> str:
        return f"Alarm({'TRIGGER' if self.trigger else 'RESET'})"

    def execute(self, chamber: BaseChamber):
        if self.trigger:
            chamber.trigger_alarm()
        else:
            chamber.reset_alarm()
