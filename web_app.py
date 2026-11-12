"""
遠端環境測試艙 (Chamber) Web 即時監控平台
後端架構: FastAPI + WebSocket (即時雙向通訊)
前端架構: HTML5 + CSS3 (工控暗色儀表板) + Apache ECharts (工業級高幀率曲線)
"""

import asyncio
import json
import time
import random
from typing import List, Set
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

app = FastAPI(title="Chamber Web Remote Monitor")

# ======================= 虛擬測試艙動力學模型 =======================
class ChamberSimulator:
    STATE_OFF = 0
    STATE_STANDBY = 1
    STATE_RUNNING = 2
    STATE_ALARM = 3

    STATE_NAMES = {
        STATE_OFF: ("關機 (OFF)", "#6c757d"),
        STATE_STANDBY: ("待機 (STANDBY)", "#ffc107"),
        STATE_RUNNING: ("運轉中 (RUNNING)", "#28a745"),
        STATE_ALARM: ("警報異常 (ALARM)", "#dc3545"),
    }

    def __init__(self):
        self.state = self.STATE_OFF
        self.ambient_temp = 25.0
        self.ambient_humi = 55.0

        self.current_temp = 25.0
        self.current_humi = 55.0
        self.target_temp = 60.0
        self.target_humi = 75.0

        self.door_open = False
        self.sim_speed = 1.0
        self.heater_active = False
        self.cooler_active = False
        self.humidifier_active = False
        self.dehumidifier_active = False

        self.total_runtime_sec = 0.0

    def set_power(self, on: bool):
        if on:
            if self.state == self.STATE_OFF:
                self.state = self.STATE_STANDBY
        else:
            self.state = self.STATE_OFF
            self.heater_active = False
            self.cooler_active = False
            self.humidifier_active = False
            self.dehumidifier_active = False

    def start_running(self):
        if self.state in (self.STATE_STANDBY, self.STATE_ALARM):
            self.state = self.STATE_RUNNING

    def pause_standby(self):
        if self.state == self.STATE_RUNNING:
            self.state = self.STATE_STANDBY

    def trigger_alarm(self):
        self.state = self.STATE_ALARM
        self.heater_active = False
        self.cooler_active = False
        self.humidifier_active = False
        self.dehumidifier_active = False

    def reset_alarm(self):
        if self.state == self.STATE_ALARM:
            self.state = self.STATE_STANDBY

    def toggle_door(self):
        self.door_open = not self.door_open
        return self.door_open

    def update(self, dt_sec: float):
        dt = dt_sec * self.sim_speed
        if self.state == self.STATE_RUNNING:
            self.total_runtime_sec += dt

        if self.door_open:
            self.current_temp += (self.ambient_temp - self.current_temp) * min(1.0, 0.4 * dt)
            self.current_humi += (self.ambient_humi - self.current_humi) * min(1.0, 0.3 * dt)
            self.heater_active = False
            self.cooler_active = False
            self.humidifier_active = False
            self.dehumidifier_active = False
            return

        if self.state == self.STATE_RUNNING:
            temp_diff = self.target_temp - self.current_temp
            if abs(temp_diff) > 0.15:
                rate = 1.8 if temp_diff > 0 else 1.4
                self.heater_active = temp_diff > 0
                self.cooler_active = temp_diff < 0
                step = rate * dt * (1.0 if temp_diff > 0 else -1.0)
                if abs(step) > abs(temp_diff):
                    self.current_temp = self.target_temp
                else:
                    self.current_temp += step
            else:
                self.heater_active = False
                self.cooler_active = False
                self.current_temp += random.uniform(-0.06, 0.06)

            humi_diff = self.target_humi - self.current_humi
            if abs(humi_diff) > 0.3:
                h_rate = 2.2 if humi_diff > 0 else 1.8
                self.humidifier_active = humi_diff > 0
                self.dehumidifier_active = humi_diff < 0
                h_step = h_rate * dt * (1.0 if humi_diff > 0 else -1.0)
                if abs(h_step) > abs(humi_diff):
                    self.current_humi = self.target_humi
                else:
                    self.current_humi += h_step
            else:
                self.humidifier_active = False
                self.dehumidifier_active = False
                self.current_humi += random.uniform(-0.15, 0.15)

        elif self.state in (self.STATE_OFF, self.STATE_STANDBY, self.STATE_ALARM):
            self.heater_active = False
            self.cooler_active = False
            self.humidifier_active = False
            self.dehumidifier_active = False
            self.current_temp += (self.ambient_temp - self.current_temp) * min(1.0, 0.05 * dt)
            self.current_humi += (self.ambient_humi - self.current_humi) * min(1.0, 0.05 * dt)

        self.current_temp = max(-50.0, min(180.0, self.current_temp))
        self.current_humi = max(5.0, min(99.0, self.current_humi))


simulator = ChamberSimulator()
active_websockets: Set[WebSocket] = set()

# 背景定時物理模擬與推播任務
async def simulation_loop():
    last_t = time.time()
    while True:
        await asyncio.sleep(0.15)
        now = time.time()
        dt = now - last_t
        last_t = now
        simulator.update(dt)

        if active_websockets:
            st_text, st_color = ChamberSimulator.STATE_NAMES[simulator.state]
            sec = int(simulator.total_runtime_sec)
            uptime_str = f"{sec // 3600:02d}:{(sec % 3600) // 60:02d}:{sec % 60:02d}"

            payload = json.dumps({
                "time": time.strftime("%H:%M:%S"),
                "temp_pv": round(simulator.current_temp, 2),
                "temp_sv": round(simulator.target_temp, 2),
                "humi_pv": round(simulator.current_humi, 2),
                "humi_sv": round(simulator.target_humi, 2),
                "state": simulator.state,
                "state_text": st_text,
                "state_color": st_color,
                "heater": simulator.heater_active,
                "cooler": simulator.cooler_active,
                "humidifier": simulator.humidifier_active,
                "door_open": simulator.door_open,
                "uptime": uptime_str,
                "sim_speed": simulator.sim_speed,
            })

            # 廣播至所有已連線網頁客戶端
            stale = []
            for ws in active_websockets:
                try:
                    await ws.send_text(payload)
                except Exception:
                    stale.append(ws)
            for ws in stale:
                active_websockets.discard(ws)


@app.on_event("startup")
async def startup_event():
    asyncio.create_task(simulation_loop())


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_websockets.add(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            cmd = json.loads(data)
            action = cmd.get("action")

            if action == "power_toggle":
                simulator.set_power(cmd.get("value", True))
            elif action == "run_toggle":
                if simulator.state == ChamberSimulator.STATE_RUNNING:
                    simulator.pause_standby()
                elif simulator.state in (ChamberSimulator.STATE_STANDBY, ChamberSimulator.STATE_ALARM):
                    simulator.start_running()
            elif action == "door_toggle":
                simulator.toggle_door()
            elif action == "alarm_toggle":
                if simulator.state == ChamberSimulator.STATE_ALARM:
                    simulator.reset_alarm()
                else:
                    simulator.trigger_alarm()
            elif action == "set_sv":
                if "temp" in cmd:
                    simulator.target_temp = float(cmd["temp"])
                if "humi" in cmd:
                    simulator.target_humi = float(cmd["humi"])
            elif action == "set_speed":
                simulator.sim_speed = float(cmd.get("value", 1.0))

    except WebSocketDisconnect:
        active_websockets.discard(websocket)
    except Exception:
        active_websockets.discard(websocket)


HTML_CONTENT = """
<!DOCTYPE html>
<html lang="zh-TW">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>遠端環境測試艙 (Chamber) 即時網頁監控中心</title>
  <!-- ECharts CDN -->
  <script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
  <style>
    :root {
      --bg-dark: #0f131a;
      --card-bg: #181d28;
      --border-color: #272f42;
      --text-main: #e2e8f0;
      --text-sub: #8d9bb0;
      --temp-color: #ff9800;
      --humi-color: #00bcd4;
      --success: #22c55e;
      --danger: #ef4444;
      --warning: #f59e0b;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: var(--bg-dark);
      color: var(--text-main);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Microsoft JhengHei", sans-serif;
      padding: 16px 24px;
      min-height: 100vh;
    }
    .header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 16px;
      padding-bottom: 12px;
      border-bottom: 1px solid var(--border-color);
    }
    .header h1 {
      font-size: 20px;
      display: flex;
      align-items: center;
      gap: 10px;
    }
    .conn-badge {
      font-size: 13px;
      padding: 4px 10px;
      border-radius: 20px;
      background: rgba(34, 197, 94, 0.15);
      color: var(--success);
      font-weight: 600;
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }
    .conn-badge.offline {
      background: rgba(239, 68, 68, 0.15);
      color: var(--danger);
    }
    .cards-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 14px;
      margin-bottom: 16px;
    }
    .card {
      background: var(--card-bg);
      border: 1px solid var(--border-color);
      border-radius: 10px;
      padding: 14px 18px;
    }
    .card-top {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 8px;
    }
    .card-title {
      font-size: 12px;
      color: var(--text-sub);
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }
    .badge {
      font-size: 11px;
      padding: 2px 8px;
      border-radius: 4px;
      background: #232b3c;
    }
    .card-val {
      font-size: 34px;
      font-weight: 800;
      font-family: "Consolas", monospace;
      margin-bottom: 6px;
    }
    .card-sub {
      font-size: 12px;
      color: var(--text-sub);
    }
    .status-badge-lg {
      font-size: 18px;
      font-weight: 700;
      padding: 8px 12px;
      border-radius: 6px;
      text-align: center;
      color: white;
      margin-bottom: 8px;
    }
    .chart-box {
      background: var(--card-bg);
      border: 1px solid var(--border-color);
      border-radius: 10px;
      padding: 16px;
      margin-bottom: 16px;
      height: 480px;
    }
    .control-panel {
      background: var(--card-bg);
      border: 1px solid var(--border-color);
      border-radius: 10px;
      padding: 16px;
      display: flex;
      flex-wrap: wrap;
      gap: 20px;
      align-items: center;
    }
    .ctrl-group {
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .ctrl-label {
      font-size: 13px;
      color: var(--text-sub);
      font-weight: 600;
    }
    button {
      background: #273043;
      color: var(--text-main);
      border: 1px solid #3c4864;
      padding: 8px 14px;
      border-radius: 6px;
      font-size: 13px;
      cursor: pointer;
      font-weight: 600;
      transition: all 0.2s;
    }
    button:hover { background: #35425c; border-color: #55678d; }
    button.btn-primary { background: #2563eb; border-color: #3b82f6; }
    button.btn-primary:hover { background: #1d4ed8; }
    button.btn-danger { background: #dc2626; border-color: #ef4444; }
    button.btn-danger:hover { background: #b91c1c; }
    button.btn-success { background: #16a34a; border-color: #22c55e; }
    button.btn-success:hover { background: #15803d; }
    input[type="number"], select {
      background: #0f131a;
      color: var(--text-main);
      border: 1px solid #3c4864;
      padding: 6px 10px;
      border-radius: 6px;
      font-size: 13px;
      width: 80px;
    }
  </style>
</head>
<body>

  <div class="header">
    <h1>⚡ 智慧環境測試艙 (Chamber) 遠端網頁監控中心</h1>
    <div>
      <span id="connBadge" class="conn-badge">● WebSocket 連線中</span>
      <span id="clock" style="margin-left: 16px; color: var(--text-sub); font-family: monospace;">--:--:--</span>
    </div>
  </div>

  <!-- 4 張指標卡片 -->
  <div class="cards-grid">
    <div class="card">
      <div class="card-top">
        <span class="card-title">艙內溫度 (PV / SV)</span>
        <span id="tagTemp" class="badge">待機中</span>
      </div>
      <div class="card-val" style="color: var(--temp-color);"><span id="valTemp">25.0</span> <span style="font-size:16px;">°C</span></div>
      <div class="card-sub">目標設定 (SV): <span id="svTemp">60.0</span> °C</div>
    </div>

    <div class="card">
      <div class="card-top">
        <span class="card-title">艙內濕度 (PV / SV)</span>
        <span id="tagHumi" class="badge">待機中</span>
      </div>
      <div class="card-val" style="color: var(--humi-color);"><span id="valHumi">55.0</span> <span style="font-size:16px;">%RH</span></div>
      <div class="card-sub">目標設定 (SV): <span id="svHumi">75.0</span> %RH</div>
    </div>

    <div class="card">
      <div class="card-top">
        <span class="card-title">機台運作主狀態</span>
        <span class="badge">CHAMBER-01</span>
      </div>
      <div id="stateBadge" class="status-badge-lg" style="background-color: #6c757d;">關機 (OFF)</div>
      <div class="card-sub">累積運轉時間: <span id="valUptime">00:00:00</span></div>
    </div>

    <div class="card">
      <div class="card-top">
        <span class="card-title">執行器與箱門感測</span>
      </div>
      <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; font-size: 13px; margin-top: 4px;">
        <div id="indHeater">加熱: OFF</div>
        <div id="indCooler">製冷: OFF</div>
        <div id="indHumid">加濕: OFF</div>
        <div id="indDoor" style="color: #22c55e;">箱門: 關閉</div>
      </div>
    </div>
  </div>

  <!-- ECharts 趨勢圖表 (溫濕度 + 狀態階梯圖) -->
  <div id="echartContainer" class="chart-box"></div>

  <!-- 遠端控制面板 -->
  <div class="control-panel">
    <div class="ctrl-group">
      <button id="btnPower" onclick="togglePower()">電源 開啟</button>
      <button id="btnRun" onclick="toggleRun()">開始運轉</button>
    </div>

    <div class="ctrl-group">
      <span class="ctrl-label">目標溫度:</span>
      <input type="number" id="inTemp" value="60" step="1" onchange="sendSV()">
      <span class="ctrl-label">°C</span>
      <span class="ctrl-label" style="margin-left: 10px;">目標濕度:</span>
      <input type="number" id="inHumi" value="75" step="1" onchange="sendSV()">
      <span class="ctrl-label">%RH</span>
    </div>

    <div class="ctrl-group">
      <button id="btnDoor" onclick="toggleDoor()">模擬開門</button>
      <button id="btnAlarm" class="btn-danger" onclick="toggleAlarm()">觸發超溫警報</button>
    </div>

    <div class="ctrl-group">
      <span class="ctrl-label">模擬加速:</span>
      <select id="selSpeed" onchange="sendSpeed(this.value)">
        <option value="1">1.0x (即時)</option>
        <option value="2">2.0x (加速)</option>
        <option value="5">5.0x (快速)</option>
        <option value="10">10.0x (極速)</option>
      </select>
      <button onclick="downloadCSV()">匯出 CSV 日誌</button>
    </div>
  </div>

  <script>
    // 初始化 ECharts
    const chart = echarts.init(document.getElementById('echartContainer'), 'dark');
    
    const MAX_PTS = 150;
    const historyData = {
      times: [],
      tempPV: [],
      tempSV: [],
      humiPV: [],
      humiSV: [],
      states: []
    };

    const option = {
      backgroundColor: 'transparent',
      tooltip: { trigger: 'axis' },
      legend: {
        data: ['溫度 PV', '溫度 SV', '濕度 PV', '濕度 SV', '機台狀態階梯'],
        top: 0
      },
      grid: [
        { left: '4%', right: '3%', top: '10%', height: '56%' },
        { left: '4%', right: '3%', top: '74%', height: '20%' }
      ],
      xAxis: [
        { type: 'category', data: historyData.times, gridIndex: 0, show: false },
        { type: 'category', data: historyData.times, gridIndex: 1, boundaryGap: false }
      ],
      yAxis: [
        { type: 'value', name: '溫濕度數值', gridIndex: 0, min: -20, max: 120 },
        { 
          type: 'value', 
          name: '機台狀態', 
          gridIndex: 1, 
          min: 0, 
          max: 3, 
          interval: 1,
          axisLabel: {
            formatter: (v) => ['關機', '待機', '運轉', '警報'][v] || v
          }
        }
      ],
      series: [
        {
          name: '溫度 PV',
          type: 'line',
          xAxisIndex: 0,
          yAxisIndex: 0,
          smooth: true,
          itemStyle: { color: '#ff9800' },
          data: historyData.tempPV
        },
        {
          name: '溫度 SV',
          type: 'line',
          xAxisIndex: 0,
          yAxisIndex: 0,
          lineStyle: { type: 'dashed', color: '#ffb74d' },
          data: historyData.tempSV
        },
        {
          name: '濕度 PV',
          type: 'line',
          xAxisIndex: 0,
          yAxisIndex: 0,
          smooth: true,
          itemStyle: { color: '#00bcd4' },
          data: historyData.humiPV
        },
        {
          name: '濕度 SV',
          type: 'line',
          xAxisIndex: 0,
          yAxisIndex: 0,
          lineStyle: { type: 'dashed', color: '#80deea' },
          data: historyData.humiSV
        },
        {
          name: '機台狀態階梯',
          type: 'line',
          step: 'middle',
          xAxisIndex: 1,
          yAxisIndex: 1,
          itemStyle: { color: '#22c55e' },
          areaStyle: { color: 'rgba(34, 197, 94, 0.2)' },
          data: historyData.states
        }
      ]
    };
    chart.setOption(option);
    window.addEventListener('resize', () => chart.resize());

    // WebSocket 通訊連線
    let ws;
    let isPowerOn = false;
    let isRunning = false;
    let isDoorOpen = false;
    let isAlarm = false;

    function connectWS() {
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      ws = new WebSocket(`${protocol}//${window.location.host}/ws`);

      ws.onopen = () => {
        const badge = document.getElementById('connBadge');
        badge.textContent = '● WebSocket 連線正常 (即時同步)';
        badge.classList.remove('offline');
      };

      ws.onmessage = (event) => {
        const d = JSON.parse(event.data);
        
        // 更新卡片
        document.getElementById('clock').textContent = d.time;
        document.getElementById('valTemp').textContent = d.temp_pv.toFixed(1);
        document.getElementById('svTemp').textContent = d.temp_sv.toFixed(1);
        document.getElementById('valHumi').textContent = d.humi_pv.toFixed(1);
        document.getElementById('svHumi').textContent = d.humi_sv.toFixed(1);
        document.getElementById('valUptime').textContent = d.uptime;

        const stateBadge = document.getElementById('stateBadge');
        stateBadge.textContent = d.state_text;
        stateBadge.style.backgroundColor = d.state_color;

        // 狀態同步
        isPowerOn = (d.state !== 0);
        isRunning = (d.state === 2);
        isDoorOpen = d.door_open;
        isAlarm = (d.state === 3);

        const btnPower = document.getElementById('btnPower');
        btnPower.textContent = isPowerOn ? '電源 關閉' : '電源 開啟';
        btnPower.className = isPowerOn ? 'btn-danger' : '';

        const btnRun = document.getElementById('btnRun');
        btnRun.textContent = isRunning ? '暫停運轉' : '開始運轉';
        btnRun.className = isRunning ? 'btn-success' : '';

        const btnDoor = document.getElementById('btnDoor');
        btnDoor.textContent = isDoorOpen ? '關閉箱門' : '模擬開門';
        btnDoor.style.backgroundColor = isDoorOpen ? '#d97706' : '';

        const btnAlarm = document.getElementById('btnAlarm');
        btnAlarm.textContent = isAlarm ? '解除警報' : '觸發超溫警報';

        // 致動器燈號
        document.getElementById('indHeater').textContent = `加熱: ${d.heater ? 'ON 🔥' : 'OFF'}`;
        document.getElementById('indHeater').style.color = d.heater ? '#ff5722' : '#8d9bb0';

        document.getElementById('indCooler').textContent = `製冷: ${d.cooler ? 'ON ❄️' : 'OFF'}`;
        document.getElementById('indCooler').style.color = d.cooler ? '#03a9f4' : '#8d9bb0';

        document.getElementById('indHumid').textContent = `加濕: ${d.humidifier ? 'ON 💧' : 'OFF'}`;
        document.getElementById('indHumid').style.color = d.humidifier ? '#00bcd4' : '#8d9bb0';

        const indDoor = document.getElementById('indDoor');
        indDoor.textContent = `箱門: ${d.door_open ? '開啟 ⚠️' : '關閉'}`;
        indDoor.style.color = d.door_open ? '#ef4444' : '#22c55e';

        // 標籤提示
        document.getElementById('tagTemp').textContent = d.heater ? '加熱中' : (d.cooler ? '製冷中' : '恆溫中');
        document.getElementById('tagHumi').textContent = d.humidifier ? '加濕中' : '恆濕中';

        // 圖表數據追加
        historyData.times.push(d.time);
        historyData.tempPV.push(d.temp_pv);
        historyData.tempSV.push(d.temp_sv);
        historyData.humiPV.push(d.humi_pv);
        historyData.humiSV.push(d.humi_sv);
        historyData.states.push(d.state);

        if (historyData.times.length > MAX_PTS) {
          historyData.times.shift();
          historyData.tempPV.shift();
          historyData.tempSV.shift();
          historyData.humiPV.shift();
          historyData.humiSV.shift();
          historyData.states.shift();
        }

        chart.setOption({
          xAxis: [
            { data: historyData.times },
            { data: historyData.times }
          ],
          series: [
            { data: historyData.tempPV },
            { data: historyData.tempSV },
            { data: historyData.humiPV },
            { data: historyData.humiSV },
            { data: historyData.states }
          ]
        });
      };

      ws.onclose = () => {
        const badge = document.getElementById('connBadge');
        badge.textContent = '❌ 連線中斷，正在重試...';
        badge.classList.add('offline');
        setTimeout(connectWS, 2000);
      };
    }

    connectWS();

    // 遠端控制函式
    function togglePower() {
      ws.send(JSON.stringify({ action: 'power_toggle', value: !isPowerOn }));
    }

    function toggleRun() {
      ws.send(JSON.stringify({ action: 'run_toggle' }));
    }

    function toggleDoor() {
      ws.send(JSON.stringify({ action: 'door_toggle' }));
    }

    function toggleAlarm() {
      ws.send(JSON.stringify({ action: 'alarm_toggle' }));
    }

    function sendSV() {
      const t = parseFloat(document.getElementById('inTemp').value);
      const h = parseFloat(document.getElementById('inHumi').value);
      ws.send(JSON.stringify({ action: 'set_sv', temp: t, humi: h }));
    }

    function sendSpeed(spd) {
      ws.send(JSON.stringify({ action: 'set_speed', value: parseFloat(spd) }));
    }

    function downloadCSV() {
      if (historyData.times.length === 0) return alert('目前尚無數據');
      let csv = '時間,溫度PV(°C),溫度SV(°C),濕度PV(%RH),濕度SV(%RH),狀態代碼\\n';
      for (let i = 0; i < historyData.times.length; i++) {
        csv += `${historyData.times[i]},${historyData.tempPV[i]},${historyData.tempSV[i]},${historyData.humiPV[i]},${historyData.humiSV[i]},${historyData.states[i]}\\n`;
      }
      const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `chamber_web_log_${new Date().toISOString().slice(0,19).replace(/[:T]/g, '_')}.csv`;
      a.click();
    }
  </script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
async def get_index():
    return HTML_CONTENT

if __name__ == "__main__":
    import uvicorn
    # 支援區網其他裝置 (0.0.0.0:8000)
    uvicorn.run("web_app:app", host="0.0.0.0", port=8000, reload=False)
