# 智慧溫濕度試驗艙 (Chamber) 監控系統

本專案採用**模組化分層架構（Layered Architecture）**，將系統清晰劃分為 **網頁 GUI（web_gui）**、**儀器設備層（chamber）** 與 **命令控制層（commands）**，達成高內聚、低耦合的工控軟體設計。

---

## 🏗️ 系統架構分層

```
Chamber monitor/
│
├── chamber/                   # 1. 儀器設備層 (Chamber Driver & Dynamics)
│   ├── base.py                # 抽象儀器介面 (未來可無縫對接 Modbus/RS485/SCPI 真實機台)
│   ├── virtual_chamber.py    # 虛擬環境試驗箱熱力學與濕度模擬器
│   └── __init__.py
│
├── commands/                  # 2. 命令控制層 (Command Pattern & Controller)
│   ├── base.py                # 命令模式定義 (Power, Run, SetTarget, Door, Alarm)
│   ├── controller.py          # 核心控制器 (統籌命令派送、日誌追蹤與遙測採集)
│   ├── cli.py                 # 命令列交互工具 (終端機直接下指令與監看)
│   └── __init__.py
│
├── web_gui/                   # 3. 網頁視覺化層 (Web GUI)
│   ├── server.py              # FastAPI + WebSocket 高頻雙向即時伺服器
│   ├── templates/
│   │   └── index.html         # 工業級深色儀表板 (HTML5 + Apache ECharts)
│   └── __init__.py
│
├── main.py                    # 桌面版應用程式入口 (PyQt6 + pyqtgraph)
├── run_web.py                 # 網頁版應用程式入口 (Web GUI Server)
├── run.bat                    # 桌面版一鍵啟動腳本
├── run_web.bat                # 網頁版一鍵啟動腳本 (自動開瀏覽器)
└── run_cli.bat                # 終端命令列一鍵啟動腳本
```

---

## 🧩 各層模組詳細說明

### 1. 儀器層 (`chamber/`)
- **責任**：專注於硬體通訊或物理模擬，完全不依賴任何圖形介面。
- **[`chamber.base.BaseChamber`](file:///d:/Chamber%20monitor/chamber/base.py)**：定義標準儀器協議（開關機、啟停、設定 SV 溫濕度、讀取 PV 溫濕度與狀態）。
- **[`chamber.virtual_chamber.VirtualChamber`](file:///d:/Chamber%20monitor/chamber/virtual_chamber.py)**：虛擬動力學模擬，提供加熱、製冷、加濕、除濕、開門散逸、超溫報警等熱力學物理表現。

### 2. 命令控制層 (`commands/`)
- **責任**：以 **Command Pattern** 封裝所有控制操作，提供安全驗證、派發與日誌紀錄。
- **[`commands.controller.ChamberController`](file:///d:/Chamber%20monitor/commands/controller.py)**：單一職責調度器，提供 `power()`, `run()`, `set_target()`, `toggle_door()`, `alarm()` 等統一介面，讓 Web GUI、Desktop GUI 與 CLI 呼叫相同邏輯。
- **[`commands.cli`](file:///d:/Chamber%20monitor/commands/cli.py)**：獨立的終端機互動介面，方便無介面環境或自動化腳本除錯。

### 3. 網頁 GUI 層 (`web_gui/`)
- **責任**：跨平台視覺化與遠端操控，任何手機、平板、電腦透過瀏覽器即可監控。
- **[`web_gui.server`](file:///d:/Chamber%20monitor/web_gui/server.py)**：FastAPI + WebSocket 廣播遙測數據（每秒約 7 次）。
- **[`web_gui/templates/index.html`](file:///d:/Chamber%20monitor/web_gui/templates/index.html)**：現代工控深色主題，內嵌 **Apache ECharts** 動態雙曲線圖、狀態階梯圖與即時按鈕。

---

## 🚀 啟動方式

| 模式 | 啟動腳本 | 終端機指令 | 說明 |
| :--- | :--- | :--- | :--- |
| **外網分享 Demo** | [`share_to_internet.bat`](file:///d:/Chamber%20monitor/share_to_internet.bat) | `.\share_to_internet.bat` | 一鍵生成外網專屬 HTTPS 網址，免設路由器即可給其他人連線！ |
| **網頁 GUI** | [`run_web.bat`](file:///d:/Chamber%20monitor/run_web.bat) | `.\venv\Scripts\python.exe run_web.py` | 本機/區網訪問 `http://localhost:8000` |
| **桌面 GUI** | [`run.bat`](file:///d:/Chamber%20monitor/run.bat) | `.\venv\Scripts\python.exe main.py` | PyQt6 原生視窗程式 |
| **終端 CLI** | [`run_cli.bat`](file:///d:/Chamber%20monitor/run_cli.bat) | `.\venv\Scripts\python.exe -m commands.cli` | 命令列文字交互與監看 |
