# CopyTrade Pro

A high-performance, open-source trade copier for MT5 and cTrader platforms. No EA or BOT required.

## Features

- **MT5 → MT5** copy trading
- **cTrader → MT5** copy trading  
- **MT5 → cTrader** copy trading
- Low latency using direct API connections
- Simple configuration via Web UI
- Real-time position monitoring
- Risk management (lot multiplier, max lot, symbol mapping)

## Architecture

```
┌─────────────────────────────────────────────┐
│           CopyTrade Engine                  │
│         (async queue processing)           │
├──────────────┬────────────────────────────┤
│  MT5 Bridge  │  cTrader OpenAPI Bridge │
├──────────────┴────────────────────────────┤
│           FastAPI Server                   │
└─────────────────────────────────────────────┘
```

## Requirements

- Python 3.11+
- MetaTrader 5 account (Windows)
- cTrader account with OpenAPI access

## Installation

```bash
pip install -r requirements.txt
```

## Quick Start

### 1. Configure Master Account

```bash
# Edit config.json
{
  "master": {
    "platform": "mt5",
    "login": "123456",
    "server": "Broker-Server",
    "password": "your_password"
  }
}
```

### 2. Run Server

```bash
python api/main.py
```

### 3. Access Web UI

Open http://localhost:8000 in your browser.

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/status` | GET | Get copy engine status |
| `/api/settings` | GET/POST | Get/update settings |
| `/api/connect` | POST | Connect master account |
| `/api/start` | POST | Start copying |
| `/api/stop` | POST | Stop copying |
| `/api/positions` | GET | Get all positions |

## Configuration Options

| Option | Description | Default |
|--------|-------------|---------|
| `lot_multiplier` | Master lot multiplied by this | 1.0 |
| `max_lot` | Maximum lot per trade | 100.0 |
| `min_lot` | Minimum lot per trade | 0.01 |
| `reverse_trades` | Reverse BUY/SELL | false |
| `copy_sl` | Copy stop loss | true |
| `copy_tp` | Copy take profit | true |
| `symbol_map` | Map symbols between platforms | {} |

## Example symbol_map

```json
{
  "symbol_map": {
    "EURUSD": "EURUSD",
    "XAUUSD": "XAUUSD"
  }
}
```

## Development

```bash
# Run API server
uvicorn api.main:app --reload

# Run tests
python -m pytest
```

## Latency

Target latency: <10ms between platforms (local execution)

## Inspired by

- [Copiix](https://copiix.com/) - Free Trade Copier
- [OpenClaw MT5 Bridge](https://github.com/Geowahaha/OpenClaw-MT5-python-bridge)

## License

MIT License