# 智慧溫濕度試驗艙 (Chamber) 監控系統 (API 解耦雙層架構)

本專案採用 **API 驅動模組化分層架構（API-Driven Layered Architecture）**，將系統劃分為：
1. **儀器設備與儀器 API 層（`chamber/`）**：擷取機台感測器數據，並透過 **儀器端 API 傳送器 (`InstrumentAPIClient`)** 將資料傳送到 Web UI 的 API 接口。
2. **Web UI 介面與資料 API 中心（`web_gui/`）**：提供標準 REST API 接口接收儀器傳來的資料，並讓前端 **Web UI 介面連接 API 讀取與即時展示數據 (Show Data)**。
3. **命令控制層（`commands/`）**：封裝控制指令（開關機、啟停、設定目標溫濕度 SV、開關箱門、超溫警報、預約排程）。

---

## 🔄 資料流與 API 傳送架構

```
[ 儀器層 Chamber / VirtualChamber ]
        │
        ▼  (擷取溫濕度 PV/SV 與狀態)
[ 儀器端 API (chamber/instrument_api.py) ]
        │
        │  HTTP POST /api/telemetry
        │  HTTP POST /api/chambers/{chamber_id}/telemetry
        ▼
[ Web UI API 接口 (web_gui/server.py) ]
        │
        ├─► GET  /api/telemetry                      (Web UI 讀取所有機台即時資料 Show Data)
        ├─► GET  /api/chambers/{chamber_id}/telemetry (Web UI 讀取單機台即時與歷史曲線)
        ├─► POST /api/chambers/{chamber_id}/command   (Web UI 下達控制指令並回傳給儀器 API)
        └─► WS   /ws                                 (WebSocket 即時雙向同步推播)
        │
        ▼
[ Web UI 視覺化儀表板 (web_gui/templates/index.html) ]
```

---

## 🏗️ 系統目錄結構

```
Chamber monitor/
│
├── chamber/                   # 1. 儀器設備與儀器 API 層
│   ├── base.py                # 抽象儀器介面與標準 API 資料序列化 (to_api_dict)
│   ├── virtual_chamber.py    # 虛擬環境試驗箱熱力學與排程模擬器
│   ├── instrument_api.py      # 儀器端 API 服務與傳送器 (主動 POST 資料至 Web UI API)
│   └── __init__.py
│
├── commands/                  # 2. 命令控制層 (Command Pattern & Controller)
│   ├── base.py                # 命令模式定義 (Power, Run, SetTarget, Door, Alarm)
│   ├── controller.py          # 多機台調度控制器 (支援 API 指令統一派發 execute_action)
│   ├── cli.py                 # 命令列交互工具
│   └── __init__.py
│
├── web_gui/                   # 3. Web UI 介面與 API 伺服器層
│   ├── server.py              # FastAPI REST API 接口 (/api/...) + WebSocket 伺服器
│   ├── templates/
│   │   └── index.html         # 工業級深色儀表板 (連接 API 顯示數據 + 內建 API 測試面板)
│   └── __init__.py
│
├── run_web.py                 # Web UI 與 API 伺服器啟動入口 (Port 8000)
├── run_instrument.py          # 獨立儀器端 API 傳送服務入口 (Port 8001 -> 傳送至 Port 8000)
├── run_web.bat                # Web UI 一鍵啟動腳本
└── run_instrument.bat         # 獨立儀器端 API 一鍵啟動腳本
```

---

## 🔌 Web UI API 與 儀器 API 接口清單

### 1. 儀器傳送到 Web UI 的 API 接口
- **`POST /api/telemetry`**：批次接收多台儀器傳送過來的即時遙測資料，並回傳待執行的控制指令 (`pending_commands`)。
- **`POST /api/chambers/{chamber_id}/telemetry`**：接收單一台儀器傳送過來的即時溫濕度與狀態資料。
  ```json
  {
    "source_id": "instrument-01",
    "telemetry": {
      "temp_pv": 85.0,
      "temp_sv": 85.0,
      "humi_pv": 85.0,
      "humi_sv": 85.0,
      "state": 2
    }
  }
  ```

### 2. Web UI 連接並顯示資料 (Show Data) 的 API 接口
- **`GET /api/telemetry`**：取得所有機台的最新溫濕度、運轉狀態、倒數計時與預約表。
- **`GET /api/chambers/{chamber_id}/telemetry`**：取得指定機台最新數據與歷史趨勢資料。
- **`POST /api/chambers/{chamber_id}/command`**：由 Web UI 發送控制指令（如 `power_toggle`, `run_toggle`, `set_sv`, `door_toggle`, `alarm_toggle`, `book_slot`）。
- **`GET /api/status`**：查看目前儀器 API 傳送封包數、來源 ID 與最後更新時間。
- **`GET /docs`**：FastAPI 自動生成的互動式 Swagger API 文件。

---

## 🚀 啟動方式

| 模式 | 啟動腳本 | 終端機指令 | 說明 |
| :--- | :--- | :--- | :--- |
| **Web UI + 內建儀器 API** | [`run_web.bat`](file:///d:/Chamber%20monitor/run_web.bat) | `.\venv\Scripts\python.exe run_web.py` | 瀏覽器開啟 `http://localhost:8000`，同時提供 `/api/...` 與 `/docs` |
| **獨立儀器端 API 傳送器** | [`run_instrument.bat`](file:///d:/Chamber%20monitor/run_instrument.bat) | `.\venv\Scripts\python.exe run_instrument.py` | 獨立運行於 `http://localhost:8001` 並持續透過 HTTP POST 傳送資料至 `http://localhost:8000/api/telemetry` |
| **外網分享 Demo** | [`share_to_internet.bat`](file:///d:/Chamber%20monitor/share_to_internet.bat) | `.\share_to_internet.bat` | 一鍵生成外網專屬 HTTPS 網址 |
