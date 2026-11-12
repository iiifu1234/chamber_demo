"""
核心多機台控制器 (ChamberController)
支援同時納管多台 Chamber (Chamber 1, Chamber 2, Chamber 3)
支援單台精準命令派送與多台遙測同步採集
"""

import time
import logging
from typing import Dict, Optional, List
from chamber.base import BaseChamber, ChamberTelemetry, ChamberState
from chamber.virtual_chamber import VirtualChamber
from commands.base import (
    ICommand, PowerCommand, RunCommand, SetTargetCommand,
    DoorCommand, AlarmCommand
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


class ChamberController:
    """多機台調度與控制中心"""

    def __init__(self, chambers: Optional[Dict[str, BaseChamber]] = None):
        if chambers:
            self.chambers = chambers
        else:
            # 預設建立 3 台不同特性的虛擬試驗艙
            c1 = VirtualChamber(ambient_temp=25.0, ambient_humi=55.0)
            c1.target_temp = 85.0
            c1.target_humi = 85.0

            c2 = VirtualChamber(ambient_temp=22.0, ambient_humi=50.0)
            c2.target_temp = -10.0
            c2.target_humi = 30.0

            c3 = VirtualChamber(ambient_temp=24.0, ambient_humi=60.0)
            c3.target_temp = 40.0
            c3.target_humi = 60.0

            self.chambers: Dict[str, BaseChamber] = {
                "chamber-1": c1,
                "chamber-2": c2,
                "chamber-3": c3,
            }

        self.command_history: List[str] = []

    def get_chamber(self, chamber_id: str = "chamber-1") -> BaseChamber:
        return self.chambers.get(chamber_id, next(iter(self.chambers.values())))

    def dispatch(self, chamber_id: str, command: ICommand):
        """派發命令至指定機台"""
        ch = self.get_chamber(chamber_id)
        ts = time.strftime("%H:%M:%S")
        log_entry = f"[{ts}] [{chamber_id}] 執行命令 -> {command.name}"
        logging.info(log_entry)
        self.command_history.append(log_entry)
        return command.execute(ch)

    # 針對指定機台的操作方法 (預設為 chamber-1)
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

    def get_telemetry(self, chamber_id: str = "chamber-1") -> ChamberTelemetry:
        return self.get_chamber(chamber_id).get_telemetry()

    def get_all_telemetry(self) -> Dict[str, ChamberTelemetry]:
        """同時獲取所有機台遙測"""
        return {cid: ch.get_telemetry() for cid, ch in self.chambers.items()}
