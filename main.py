"""
桌面版 PyQt6 監控介面
直接呼叫 commands.ChamberController 與 chamber 模組
"""

import sys
import time
import csv
from datetime import datetime
from collections import deque

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLabel, QPushButton, QDoubleSpinBox,
    QGroupBox, QFrame, QFileDialog, QMessageBox, QComboBox
)
from PyQt6.QtCore import Qt, QTimer
import pyqtgraph as pg

from chamber.base import ChamberState, STATE_METADATA
from commands.controller import ChamberController

# 設定 pyqtgraph 全域背景與外觀
pg.setConfigOption('background', '#161922')
pg.setConfigOption('foreground', '#D8DEE9')
pg.setConfigOption('antialias', True)


class MainWindow(QMainWindow):
    def __init__(self, controller: ChamberController = None):
        super().__init__()
        self.setWindowTitle("智慧溫濕度試驗艙 (Chamber) 桌面監控系統 - PyQt6")
        self.resize(1360, 880)
        self.setMinimumSize(1100, 700)

        # 核心控制器 (命令層)
        self.controller = controller or ChamberController()

        # 歷史資料緩衝區
        self.max_points = 300
        self.times = deque(maxlen=self.max_points)
        self.temp_pvs = deque(maxlen=self.max_points)
        self.temp_svs = deque(maxlen=self.max_points)
        self.humi_pvs = deque(maxlen=self.max_points)
        self.humi_svs = deque(maxlen=self.max_points)
        self.states = deque(maxlen=self.max_points)

        self.start_epoch = time.time()

        self._setup_ui()
        self._apply_stylesheet()

        # 定時器更新資料 (100 ms 一次)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._on_tick)
        self.timer.start(100)

    def _setup_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(16, 12, 16, 16)
        main_layout.setSpacing(12)

        # 1. 頂部標題
        header_layout = QHBoxLayout()
        title_label = QLabel("⚡ Chamber 環境試驗機 - 桌面監控介面 (Desktop GUI)")
        title_label.setObjectName("headerTitle")
        
        self.conn_label = QLabel("● 系統就緒 (Connected)")
        self.conn_label.setObjectName("connStatus")
        
        self.clock_label = QLabel()
        self.clock_label.setObjectName("clockLabel")

        header_layout.addWidget(title_label)
        header_layout.addStretch()
        header_layout.addWidget(self.conn_label)
        header_layout.addSpacing(20)
        header_layout.addWidget(self.clock_label)
        main_layout.addLayout(header_layout)

        # 2. 核心指標儀表卡片
        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(12)

        self.temp_card = self._create_card("溫度 (TEMPERATURE)", "PV", "25.0", "°C", "#FF8A00")
        self.temp_val_label = self.temp_card.findChild(QLabel, "metricValue")
        self.temp_sv_label = self.temp_card.findChild(QLabel, "metricSV")
        self.temp_tag = self.temp_card.findChild(QLabel, "metricTag")
        cards_layout.addWidget(self.temp_card)

        self.humi_card = self._create_card("濕度 (HUMIDITY)", "PV", "55.0", "%RH", "#00C0FF")
        self.humi_val_label = self.humi_card.findChild(QLabel, "metricValue")
        self.humi_sv_label = self.humi_card.findChild(QLabel, "metricSV")
        self.humi_tag = self.humi_card.findChild(QLabel, "metricTag")
        cards_layout.addWidget(self.humi_card)

        self.state_card = self._create_state_card()
        cards_layout.addWidget(self.state_card)

        self.io_card = self._create_io_card()
        cards_layout.addWidget(self.io_card)

        main_layout.addLayout(cards_layout)

        # 3. 趨勢曲線圖表區 (pyqtgraph)
        self.plot_widget = pg.GraphicsLayoutWidget()
        self.plot_widget.setObjectName("plotWidget")

        self.p_temp = self.plot_widget.addPlot(row=0, col=0, title="<span style='color:#FF8A00;font-weight:bold;'>■ 溫度曲線 (°C)</span>  |  <span style='color:#00C0FF;font-weight:bold;'>■ 濕度曲線 (%RH)</span>")
        self.p_temp.showGrid(x=True, y=True, alpha=0.25)
        self.p_temp.setLabel('left', '數值 (Values)')
        self.p_temp.addLegend(offset=(10, 10))

        self.curve_temp_pv = self.p_temp.plot(pen=pg.mkPen('#FF8A00', width=2.5), name='溫度 PV')
        self.curve_temp_sv = self.p_temp.plot(pen=pg.mkPen('#FFA726', width=1.5, style=Qt.PenStyle.DashLine), name='溫度 SV')
        self.curve_humi_pv = self.p_temp.plot(pen=pg.mkPen('#00C0FF', width=2.5), name='濕度 PV')
        self.curve_humi_sv = self.p_temp.plot(pen=pg.mkPen('#80DEEA', width=1.5, style=Qt.PenStyle.DashLine), name='濕度 SV')

        self.p_state = self.plot_widget.addPlot(row=1, col=0)
        self.p_state.setMaximumHeight(130)
        self.p_state.setXLink(self.p_temp)
        self.p_state.showGrid(x=True, y=True, alpha=0.25)
        self.p_state.setLabel('left', '機台狀態')
        self.p_state.setLabel('bottom', '時間軸 (秒 - Seconds)')

        y_axis = self.p_state.getAxis('left')
        y_axis.setTicks([[(0, '關機 OFF'), (1, '待機 STANDBY'), (2, '運轉 RUN'), (3, '警報 ALARM')]])
        self.p_state.setYRange(-0.3, 3.3, padding=0)

        self.curve_state = self.p_state.plot(
            pen=pg.mkPen('#4CAF50', width=2.5),
            stepMode="center",
            brush=pg.mkBrush(76, 175, 80, 50),
            fillLevel=0
        )

        main_layout.addWidget(self.plot_widget, stretch=1)

        # 4. 控制操作面板
        control_panel = self._create_control_panel()
        main_layout.addWidget(control_panel)

    def _create_card(self, title, tag_name, val_default, unit, color_hex):
        card = QFrame()
        card.setObjectName("metricCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(4)

        top_h = QHBoxLayout()
        title_lbl = QLabel(title)
        title_lbl.setObjectName("cardTitle")
        tag_lbl = QLabel("IDLE")
        tag_lbl.setObjectName("metricTag")
        top_h.addWidget(title_lbl)
        top_h.addStretch()
        top_h.addWidget(tag_lbl)
        layout.addLayout(top_h)

        val_h = QHBoxLayout()
        val_lbl = QLabel(val_default)
        val_lbl.setObjectName("metricValue")
        val_lbl.setStyleSheet(f"color: {color_hex}; font-size: 32px; font-weight: bold;")
        
        unit_lbl = QLabel(unit)
        unit_lbl.setObjectName("metricUnit")
        val_h.addWidget(val_lbl)
        val_h.addWidget(unit_lbl)
        val_h.addStretch()
        layout.addLayout(val_h)

        sv_lbl = QLabel("設定值 (SV): 0.0")
        sv_lbl.setObjectName("metricSV")
        layout.addWidget(sv_lbl)

        return card

    def _create_state_card(self):
        card = QFrame()
        card.setObjectName("metricCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(4)

        title_lbl = QLabel("機台主狀態 (MACHINE STATUS)")
        title_lbl.setObjectName("cardTitle")
        layout.addWidget(title_lbl)

        self.state_badge = QLabel("關機 (OFF)")
        self.state_badge.setObjectName("stateBadge")
        self.state_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.state_badge.setStyleSheet("background-color: #495057; color: #FFFFFF; font-size: 18px; font-weight: bold; border-radius: 6px; padding: 6px;")
        layout.addWidget(self.state_badge)

        self.uptime_lbl = QLabel("累積運轉: 00:00:00")
        self.uptime_lbl.setObjectName("metricSV")
        layout.addWidget(self.uptime_lbl)

        return card

    def _create_io_card(self):
        card = QFrame()
        card.setObjectName("metricCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(4)

        title_lbl = QLabel("執行器與感測狀態 (ACTUATORS)")
        title_lbl.setObjectName("cardTitle")
        layout.addWidget(title_lbl)

        grid = QGridLayout()
        grid.setSpacing(6)

        self.ind_heater = QLabel("加熱: OFF")
        self.ind_cooler = QLabel("製冷: OFF")
        self.ind_humi = QLabel("加濕: OFF")
        self.ind_door = QLabel("箱門: 關閉")

        for lbl in (self.ind_heater, self.ind_cooler, self.ind_humi, self.ind_door):
            lbl.setStyleSheet("color: #A0AAB8; font-size: 12px; background: #232733; padding: 3px 6px; border-radius: 4px;")

        grid.addWidget(self.ind_heater, 0, 0)
        grid.addWidget(self.ind_cooler, 0, 1)
        grid.addWidget(self.ind_humi, 1, 0)
        grid.addWidget(self.ind_door, 1, 1)
        layout.addLayout(grid)

        return card

    def _create_control_panel(self):
        group = QGroupBox("命令調度與控制中心 (Command Dispatcher)")
        group.setObjectName("controlGroup")
        layout = QHBoxLayout(group)
        layout.setSpacing(16)
        layout.setContentsMargins(14, 14, 14, 12)

        power_box = QVBoxLayout()
        power_box.setSpacing(6)
        p_label = QLabel("機台主控:")
        p_label.setStyleSheet("font-weight: bold; color: #E0E0E0;")
        
        btn_h = QHBoxLayout()
        self.btn_power = QPushButton("電源 開啟")
        self.btn_power.setObjectName("btnPower")
        self.btn_power.clicked.connect(self._toggle_power)

        self.btn_run = QPushButton("開始運轉")
        self.btn_run.setObjectName("btnRun")
        self.btn_run.clicked.connect(self._toggle_run)

        btn_h.addWidget(self.btn_power)
        btn_h.addWidget(self.btn_run)
        power_box.addWidget(p_label)
        power_box.addLayout(btn_h)
        layout.addLayout(power_box)

        sv_box = QVBoxLayout()
        sv_box.setSpacing(4)
        
        sv_temp_h = QHBoxLayout()
        lbl_st = QLabel("目標溫度 SV (°C):")
        self.spin_temp_sv = QDoubleSpinBox()
        self.spin_temp_sv.setRange(-40.0, 150.0)
        self.spin_temp_sv.setValue(60.0)
        self.spin_temp_sv.valueChanged.connect(self._on_sv_changed)
        sv_temp_h.addWidget(lbl_st)
        sv_temp_h.addWidget(self.spin_temp_sv)

        sv_humi_h = QHBoxLayout()
        lbl_sh = QLabel("目標濕度 SV (%RH):")
        self.spin_humi_sv = QDoubleSpinBox()
        self.spin_humi_sv.setRange(10.0, 98.0)
        self.spin_humi_sv.setValue(75.0)
        self.spin_humi_sv.valueChanged.connect(self._on_sv_changed)
        sv_humi_h.addWidget(lbl_sh)
        sv_humi_h.addWidget(self.spin_humi_sv)

        sv_box.addLayout(sv_temp_h)
        sv_box.addLayout(sv_humi_h)
        layout.addLayout(sv_box)

        sim_box = QVBoxLayout()
        sim_box.setSpacing(6)
        sim_lbl = QLabel("情境干預:")
        sim_lbl.setStyleSheet("font-weight: bold; color: #E0E0E0;")
        
        sim_btns = QHBoxLayout()
        self.btn_door = QPushButton("模擬開門")
        self.btn_door.clicked.connect(self._toggle_door)

        self.btn_alarm = QPushButton("觸發超溫警報")
        self.btn_alarm.setObjectName("btnAlarm")
        self.btn_alarm.clicked.connect(self._toggle_alarm)

        sim_btns.addWidget(self.btn_door)
        sim_btns.addWidget(self.btn_alarm)
        sim_box.addWidget(sim_lbl)
        sim_box.addLayout(sim_btns)
        layout.addLayout(sim_box)

        misc_box = QVBoxLayout()
        misc_box.setSpacing(6)
        
        speed_h = QHBoxLayout()
        speed_lbl = QLabel("模擬速度:")
        self.combo_speed = QComboBox()
        self.combo_speed.addItems(["1.0x (即時)", "2.0x (加速)", "5.0x (快速)", "10.0x (極速)"])
        self.combo_speed.currentIndexChanged.connect(self._on_speed_changed)
        speed_h.addWidget(speed_lbl)
        speed_h.addWidget(self.combo_speed)

        misc_btns = QHBoxLayout()
        self.btn_export = QPushButton("匯出 CSV 紀錄")
        self.btn_export.clicked.connect(self._export_csv)
        self.btn_clear = QPushButton("清除圖表")
        self.btn_clear.clicked.connect(self._clear_data)
        misc_btns.addWidget(self.btn_export)
        misc_btns.addWidget(self.btn_clear)

        misc_box.addLayout(speed_h)
        misc_box.addLayout(misc_btns)
        layout.addLayout(misc_box)

        return group

    def _toggle_power(self):
        t = self.controller.get_telemetry()
        if t.state == ChamberState.OFF:
            self.controller.power(True)
            self.btn_power.setText("電源 關閉")
            self.btn_power.setStyleSheet("background-color: #c0392b; color: white;")
        else:
            self.controller.power(False)
            self.btn_power.setText("電源 開啟")
            self.btn_power.setStyleSheet("")
            self.btn_run.setText("開始運轉")

    def _toggle_run(self):
        t = self.controller.get_telemetry()
        if t.state == ChamberState.RUNNING:
            self.controller.run(False)
            self.btn_run.setText("開始運轉")
            self.btn_run.setStyleSheet("")
        elif t.state in (ChamberState.STANDBY, ChamberState.ALARM):
            self.controller.run(True)
            self.btn_run.setText("暫停運轉")
            self.btn_run.setStyleSheet("background-color: #27ae60; color: white;")

    def _toggle_door(self):
        is_open = self.controller.toggle_door()
        if is_open:
            self.btn_door.setText("關閉箱門")
            self.btn_door.setStyleSheet("background-color: #d35400; color: white;")
        else:
            self.btn_door.setText("模擬開門")
            self.btn_door.setStyleSheet("")

    def _toggle_alarm(self):
        t = self.controller.get_telemetry()
        if t.state == ChamberState.ALARM:
            self.controller.alarm(False)
            self.btn_alarm.setText("觸發超溫警報")
            self.btn_alarm.setStyleSheet("")
        else:
            self.controller.alarm(True)
            self.btn_alarm.setText("解除異常警報")
            self.btn_alarm.setStyleSheet("background-color: #e74c3c; color: white; font-weight: bold;")

    def _on_sv_changed(self):
        self.controller.set_target(
            temp=self.spin_temp_sv.value(),
            humi=self.spin_humi_sv.value()
        )

    def _on_speed_changed(self, idx):
        speeds = [1.0, 2.0, 5.0, 10.0]
        self.controller.set_speed(speeds[idx])

    def _clear_data(self):
        self.times.clear()
        self.temp_pvs.clear()
        self.temp_svs.clear()
        self.humi_pvs.clear()
        self.humi_svs.clear()
        self.states.clear()
        self.start_epoch = time.time()

    def _export_csv(self):
        if not self.times:
            QMessageBox.warning(self, "警告", "目前尚無歷史數據可供匯出！")
            return

        file_path, _ = QFileDialog.getSaveFileName(self, "匯出溫濕度監控日誌", f"chamber_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv", "CSV Files (*.csv)")
        if not file_path:
            return

        try:
            with open(file_path, mode='w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(["相對時間(秒)", "溫度PV(°C)", "溫度SV(°C)", "濕度PV(%RH)", "濕度SV(%RH)", "機台狀態代碼", "機台狀態名稱"])
                for t, tp, ts, hp, hs, st in zip(self.times, self.temp_pvs, self.temp_svs, self.humi_pvs, self.humi_svs, self.states):
                    st_name, _ = STATE_METADATA.get(st, ("未知", ""))
                    writer.writerow([f"{t:.2f}", f"{tp:.2f}", f"{ts:.2f}", f"{hp:.2f}", f"{hs:.2f}", int(st), st_name])
            QMessageBox.information(self, "成功", f"歷史日誌已成功儲存至：\n{file_path}")
        except Exception as e:
            QMessageBox.critical(self, "錯誤", f"儲存失敗：{str(e)}")

    def _on_tick(self):
        t = self.controller.get_telemetry()

        current_rel_sec = time.time() - self.start_epoch
        self.times.append(current_rel_sec)
        self.temp_pvs.append(t.temp_pv)
        self.temp_svs.append(t.temp_sv)
        self.humi_pvs.append(t.humi_pv)
        self.humi_svs.append(t.humi_sv)
        self.states.append(int(t.state))

        self.clock_label.setText(datetime.now().strftime("%Y-%m-%d  %H:%M:%S"))

        self.temp_val_label.setText(f"{t.temp_pv:.1f}")
        self.temp_sv_label.setText(f"設定值 (SV): {t.temp_sv:.1f} °C")

        self.humi_val_label.setText(f"{t.humi_pv:.1f}")
        self.humi_sv_label.setText(f"設定值 (SV): {t.humi_sv:.1f} %RH")

        if t.heater:
            self.temp_tag.setText("加熱中 🔥")
            self.temp_tag.setStyleSheet("color: #ff5722; font-weight: bold;")
        elif t.cooler:
            self.temp_tag.setText("製冷中 ❄️")
            self.temp_tag.setStyleSheet("color: #03a9f4; font-weight: bold;")
        else:
            self.temp_tag.setText("恆溫中 ✓")
            self.temp_tag.setStyleSheet("color: #8bc34a; font-weight: bold;")

        if t.humidifier:
            self.humi_tag.setText("加濕中 💧")
            self.humi_tag.setStyleSheet("color: #00bcd4; font-weight: bold;")
        elif t.dehumidifier:
            self.humi_tag.setText("除濕中 💨")
            self.humi_tag.setStyleSheet("color: #ff9800; font-weight: bold;")
        else:
            self.humi_tag.setText("恆濕中 ✓")
            self.humi_tag.setStyleSheet("color: #8bc34a; font-weight: bold;")

        self.state_badge.setText(t.state_text)
        self.state_badge.setStyleSheet(f"background-color: {t.state_color}; color: #FFFFFF; font-size: 18px; font-weight: bold; border-radius: 6px; padding: 6px;")

        self.uptime_lbl.setText(f"累積運轉: {t.uptime_str}")

        self.ind_heater.setText(f"加熱: {'ON (作用中)' if t.heater else 'OFF'}")
        self.ind_heater.setStyleSheet(f"color: {'#ff5722; font-weight: bold;' if t.heater else '#A0AAB8;'}")

        self.ind_cooler.setText(f"製冷: {'ON (作用中)' if t.cooler else 'OFF'}")
        self.ind_cooler.setStyleSheet(f"color: {'#03a9f4; font-weight: bold;' if t.cooler else '#A0AAB8;'}")

        self.ind_humi.setText(f"加濕: {'ON (作用中)' if t.humidifier else 'OFF'}")
        self.ind_humi.setStyleSheet(f"color: {'#00bcd4; font-weight: bold;' if t.humidifier else '#A0AAB8;'}")

        self.ind_door.setText(f"箱門: {'開啟 (OPEN) ⚠️' if t.door_open else '關閉 (CLOSED)'}")
        self.ind_door.setStyleSheet(f"color: {'#e74c3c; font-weight: bold;' if t.door_open else '#2ecc71;'}")

        if len(self.times) > 1:
            x = list(self.times)
            self.curve_temp_pv.setData(x, list(self.temp_pvs))
            self.curve_temp_sv.setData(x, list(self.temp_svs))
            self.curve_humi_pv.setData(x, list(self.humi_pvs))
            self.curve_humi_sv.setData(x, list(self.humi_svs))
            self.curve_state.setData(x, list(self.states))

    def _apply_stylesheet(self):
        style = """
        QWidget {
            background-color: #12151C;
            color: #D8DEE9;
            font-family: "Segoe UI", "Microsoft JhengHei", sans-serif;
            font-size: 13px;
        }
        #headerTitle { font-size: 20px; font-weight: bold; color: #ECEFF4; }
        #connStatus { color: #2ecc71; font-weight: bold; font-size: 13px; }
        #clockLabel { color: #88C0D0; font-size: 14px; font-family: "Consolas", monospace; }
        #metricCard { background-color: #1A1F2C; border: 1px solid #2B3347; border-radius: 8px; }
        #cardTitle { font-size: 12px; font-weight: bold; color: #8E99AC; }
        #metricTag { font-size: 11px; padding: 2px 6px; border-radius: 4px; background: #232733; }
        #metricUnit { font-size: 14px; color: #8E99AC; margin-top: 10px; }
        #metricSV { font-size: 12px; color: #A0AAB8; }
        #controlGroup { background-color: #1A1F2C; border: 1px solid #2B3347; border-radius: 8px; font-weight: bold; color: #ECEFF4; margin-top: 8px; }
        QPushButton { background-color: #2E3440; color: #ECEFF4; border: 1px solid #434C5E; border-radius: 5px; padding: 6px 12px; font-size: 13px; }
        QPushButton:hover { background-color: #3B4252; border-color: #5E81AC; }
        QPushButton:pressed { background-color: #4C566A; }
        QDoubleSpinBox, QComboBox { background-color: #232733; color: #ECEFF4; border: 1px solid #3B4252; border-radius: 4px; padding: 4px 8px; font-size: 13px; }
        #plotWidget { border: 1px solid #2B3347; border-radius: 8px; }
        """
        self.setStyleSheet(style)


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
