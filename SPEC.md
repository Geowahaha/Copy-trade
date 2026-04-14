# CopyTrade Pro - Specification

## Project Overview
- **Name**: CopyTrade Pro (OpenCopy)
- **Type**: Cross-platform Trade Copier Application
- **Core Functionality**: Real-time trade copying between MT5 and cTrader accounts without requiring EA or BOT installation
- **Target Users**: Prop traders, fund managers, and individuals managing multiple accounts

## Architecture

### System Design
```
┌─────────────────────────────────────────────────────────────┐
│                      CopyTrade Core                        │
│                    (Python asyncio)                       │
├─────────────────────────────────────────────────────────────┤
│  MT5 Bridge  │  cTrader OpenAPI Bridge  │  Copy Engine       │
│  (MetaTrader5) │  (REST API)           │  (async queue)   │
├─────────────────────────────────────────────────────────────┤
│                    Web UI / API Server                    │
│                     (FastAPI + React)                     │
└─────────────────────────────────────────────────────────────┘
```

### Technology Stack
- **Language**: Python 3.11+
- **MT5**: `MetaTrader5` Python package
- **cTrader**: cTrader OpenAPI (REST)
- **Web Framework**: FastAPI (backend), React (frontend)
- **Database**: SQLite (local) / PostgreSQL (optional)
- **Async**: asyncio, aiohttp

## Features

### 1. Account Management
- Add/remove master accounts (MT5 or cTrader)
- Add/remove slave accounts (MT5 or cTrader)
- Support mixed platforms: MT5→MT5, MT5→cTrader, cTrader→MT5, cTrader→cTrader

### 2. Trade Copying
- Market orders copy
- Pending orders (Limit, Stop)
- Partial close handling
- SL/TP modification
- Real-time sync with minimal latency (<10ms target)

### 3. Risk Management
- Lot size multiplier per slave
- Max lot limit
- Symbol mapping/filtering
- Reverse trades option

### 4. Dashboard
- Active positions view
- Trade history
- Account equity/balance
- Latency monitoring

## API Structure

### cTrader OpenAPI
cTrader มี REST API สำหรับ trading:
- `POST /api/v3/authentication/token` - Authentication
- `GET /api/v3/accounts` - Get accounts
- `POST /api/v3/orders` - Place order
- `GET /api/v3/positions` - Get positions
- `DELETE /api/v3/orders/{id}` - Cancel order

### MT5 Bridge
ใช้ MetaTrader5 package:
- `MT5.initialize()` / `MT5.shutdown()`
- `MT5.account_info()`
- `MT5.order_send(request)`
- `MT5.positions_get()`

## File Structure
```
copytrade/
├── bridges/
│   ├── mt5_bridge.py      # MT5 connection wrapper
│   └── ctrader_bridge.py # cTrader OpenAPI wrapper
├── core/
│   ├── copy_engine.py     # Main copy logic
│   ├── order_mapper.py   # Symbol/param mapping
│   └── position_sync.py  # Position reconciliation
├── api/
│   ├── main.py           # FastAPI server
│   └── routes.py        # API endpoints
├── ui/                   # React frontend
├── config/
│   └── settings.py       # Configuration
├── requirements.txt
└── README.md
```

## Configuration (Simplified)
```json
{
  "master": {
    "platform": "mt5",
    "login": "123456",
    "server": "Broker-Server",
    "password": "xxx"
  },
  "slaves": [
    {
      "platform": "ctrader",
      "access_token": "xxx",
      "account_id": "xxx"
    }
  ]
}
```

## Development Roadmap

### Phase 1: Core Bridges
- MT5 Bridge with basic trading
- cTrader OpenAPI authentication
- Order placement/close

### Phase 2: Copy Engine
- Real-time trade detection
- Position sync
- Error handling & retry

### Phase 3: Web Interface
- Account setup UI
- Dashboard
- Settings

## References
- Copiix: https://copiix.com/
- OpenClaw MT5 Bridge: https://github.com/Geowahaha/OpenClaw-MT5-python-bridge
- cTrader OpenAPI: https://openapi.ctrader.com/