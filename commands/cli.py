"""
命令列交互工具 (Chamber Command Line Interface)
支援在終端機中直接下達指令並監看機台
"""

import sys
import time
from commands.controller import ChamberController


def print_help():
    print("""
================ Chamber 終端命令清單 ================
  status                  - 顯示當前機台狀態與溫濕度
  power <on|off>          - 主電源開關 (例如: power on)
  run <start|pause>       - 開始運轉 / 暫停待機 (例如: run start)
  set temp <數值>         - 設定目標溫度 SV (例如: set temp 85.0)
  set humi <數值>         - 設定目標濕度 SV (例如: set humi 80.0)
  door                    - 模擬切換箱門 (開/關)
  alarm <trigger|reset>   - 觸發或復歸警報 (例如: alarm trigger)
  speed <倍速>            - 設定物理模擬倍率 (例如: speed 5)
  monitor                 - 連續即時更新監控 (按 Ctrl+C 結束)
  help                    - 顯示此說明
  exit / quit             - 退出 CLI
======================================================
""")


def monitor_loop(controller: ChamberController):
    print("即時監看中 (按 Ctrl+C 返回命令行)...")
    try:
        while True:
            t = controller.get_telemetry()
            door_str = "開門⚠️" if t.door_open else "關閉"
            act_str = f"加熱:{'ON' if t.heater else 'OFF'} 製冷:{'ON' if t.cooler else 'OFF'} 加濕:{'ON' if t.humidifier else 'OFF'}"
            sys.stdout.write(f"\r[{t.timestamp}] 狀態:{t.state_text:<12} 溫:{t.temp_pv:>5.1f}°C(SV:{t.temp_sv:>4.1f}) 濕:{t.humi_pv:>5.1f}%(SV:{t.humi_sv:>4.1f}) 門:{door_str} | {act_str}")
            sys.stdout.flush()
            time.sleep(0.3)
    except KeyboardInterrupt:
        print("\n已退出即時監看模式。")


def run_cli():
    controller = ChamberController()
    print("⚡ Chamber 虛擬測試艙命令終端 (輸入 'help' 查看指令)")

    while True:
        try:
            line = input("Chamber> ").strip()
            if not line:
                continue

            parts = line.split()
            cmd = parts[0].lower()

            if cmd in ("exit", "quit", "q"):
                print("已結束 Chamber CLI。")
                break
            elif cmd == "help":
                print_help()
            elif cmd == "status":
                t = controller.get_telemetry()
                print(f"狀態: {t.state_text} (運行: {t.uptime_str})")
                print(f"溫度: PV={t.temp_pv:.1f} °C, SV={t.temp_sv:.1f} °C (加熱: {t.heater}, 製冷: {t.cooler})")
                print(f"濕度: PV={t.humi_pv:.1f} %RH, SV={t.humi_sv:.1f} %RH (加濕: {t.humidifier})")
                print(f"箱門: {'開啟 (OPEN)' if t.door_open else '關閉 (CLOSED)'}")
            elif cmd == "power" and len(parts) > 1:
                arg = parts[1].lower()
                controller.power(arg == "on")
                print(f"已發送電源指令: {arg.upper()}")
            elif cmd == "run" and len(parts) > 1:
                arg = parts[1].lower()
                controller.run(arg in ("start", "on", "1"))
                print(f"已發送運轉指令: {arg.upper()}")
            elif cmd == "set" and len(parts) >= 3:
                sub = parts[1].lower()
                val = float(parts[2])
                if sub == "temp":
                    controller.set_target(temp=val)
                    print(f"目標溫度已設定為: {val} °C")
                elif sub == "humi":
                    controller.set_target(humi=val)
                    print(f"目標濕度已設定為: {val} %RH")
            elif cmd == "door":
                opened = controller.toggle_door()
                print(f"箱門切換為: {'開啟 (OPEN)' if opened else '關閉 (CLOSED)'}")
            elif cmd == "alarm" and len(parts) > 1:
                arg = parts[1].lower()
                controller.alarm(arg == "trigger")
                print(f"警報指令: {arg.upper()}")
            elif cmd == "speed" and len(parts) > 1:
                spd = float(parts[1])
                controller.set_speed(spd)
                print(f"模擬倍速已設為: {spd}x")
            elif cmd == "monitor":
                monitor_loop(controller)
            else:
                print(f"未知指令: '{line}', 輸入 'help' 查看支援指令。")

        except Exception as e:
            print(f"執行失敗: {e}")


if __name__ == "__main__":
    run_cli()
