"""
CopyTrade Pro - FastAPI Server
Simple Web UI for configuring and monitoring copy trading
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import AppSettings, AccountConfig, load_settings, save_settings
from core.copy_engine import CopyEngine, CopyConfig, PlatformType, TradeSignal, TradeAction
from bridges.mt5_bridge import MT5Bridge
from bridges.ctrader_bridge import CToderBridge


app = FastAPI(title="CopyTrade Pro API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from fastapi.responses import FileResponse
from pathlib import Path

UI_PATH = Path(__file__).parent.parent / "ui"


class AccountIn(BaseModel):
    platform: str
    login: str
    server: str = ""
    password: str = ""
    access_token: str = ""
    refresh_token: str = ""
    account_id: str = ""


class SettingsIn(BaseModel):
    master: Optional[AccountIn] = None
    slaves: List[AccountIn] = []
    lot_multiplier: float = 1.0
    max_lot: float = 100.0
    min_lot: float = 0.01
    reverse_trades: bool = False
    copy_sl: bool = True
    copy_tp: bool = True
    symbol_map: Dict[str, str] = {}


copy_engine = CopyEngine()
monitor_task = None
mt5_bridges = []
ctrader_bridges = []
settings = None


@app.on_event("startup")
async def startup():
    global settings
    settings = load_settings()
    print("CopyTrade API started")


@app.get("/")
async def root():
    return FileResponse(UI_PATH / "index.html")


@app.get("/api/status")
async def get_status():
    if not copy_engine.running:
        return {"status": "stopped", "positions": 0}
    
    stats = copy_engine.get_stats()
    return {
        "status": "running",
        "positions": stats["active_positions"],
        "latency": stats["latency"]
    }


@app.get("/api/settings")
async def get_settings():
    global settings
    if not settings:
        settings = load_settings()
        if not settings:
            return {"master": None, "slaves": [], "lot_multiplier": 1.0}
    
    return {
        "master": settings.master.to_dict() if settings.master else None,
        "slaves": [s.to_dict() for s in (settings.slaves or [])],
        "lot_multiplier": settings.lot_multiplier or 1.0,
        "max_lot": settings.max_lot or 100.0,
        "min_lot": settings.min_lot or 0.01,
        "reverse_trades": settings.reverse_trades or False,
        "copy_sl": settings.copy_sl if hasattr(settings, 'copy_sl') else True,
        "copy_tp": settings.copy_tp if hasattr(settings, 'copy_tp') else True,
        "symbol_map": settings.symbol_map or {}
    }


@app.post("/api/settings")
async def update_settings(data: SettingsIn):
    global settings
    
    master = None
    if data.master:
        master = AccountConfig(**data.master.dict())
    
    slaves = [AccountConfig(**s.dict()) for s in data.slaves]
    
    settings = AppSettings(
        master=master,
        slaves=slaves,
        lot_multiplier=data.lot_multiplier,
        max_lot=data.max_lot,
        min_lot=data.min_lot,
        reverse_trades=data.reverse_trades,
        copy_sl=data.copy_sl,
        copy_tp=data.copy_tp,
        symbol_map=data.symbol_map
    )
    
    save_settings(settings)
    return {"status": "saved"}


@app.post("/api/connect")
async def connect_master(account: AccountIn):
    global mt5_bridges, ctrader_bridges, settings
    
    if account.platform == "mt5":
        mt5_bridge = MT5Bridge()
        success = mt5_bridge.connect(
            login=int(account.login),
            server=account.server,
            password=account.password
        )
        
        if not success:
            raise HTTPException(status_code=400, detail="MT5 connection failed")
        
        mt5_bridges.append(mt5_bridge)
        copy_engine.register_bridge(PlatformType.MT5, mt5_bridge)
        
        settings.master = AccountConfig(
            platform="mt5",
            login=account.login,
            server=account.server,
            password=account.password
        )
        save_settings(settings)
        
        return {"status": "connected", "platform": "mt5", "login": account.login}
    
    elif account.platform == "ctrader":
        ctrader_bridge = CToderBridge()
        
        if account.refresh_token:
            ctrader_bridge.set_tokens(account.access_token, account.refresh_token)
        else:
            success = ctrader_bridge.authenticate(access_token=account.access_token)
            if not success:
                raise HTTPException(status_code=400, detail="cTrader auth failed")
        
        if account.account_id:
            ctrader_bridge.set_account(account.account_id)
        
        ctrader_bridges.append(ctrader_bridge)
        copy_engine.register_bridge(PlatformType.CTRADER, ctrader_bridge)
        
        settings.master = AccountConfig(
            platform="ctrader",
            login=account.account_id,
            account_id=account.account_id,
            access_token=account.access_token,
            refresh_token=account.refresh_token
        )
        save_settings(settings)
        
        return {"status": "connected", "platform": "ctrader", "account_id": account.account_id}
    
    raise HTTPException(status_code=400, detail="Unsupported platform")


@app.post("/api/slave/add")
async def add_slave(account: AccountIn):
    global mt5_bridges, ctrader_bridges
    
    if account.platform == "mt5":
        if not account.login or not account.password:
            raise HTTPException(status_code=400, detail="Login and password required")
        
        bridge = MT5Bridge()
        success = bridge.connect(
            login=int(account.login),
            server=account.server,
            password=account.password
        )
        
        if not success:
            raise HTTPException(status_code=400, detail="MT5 connection failed")
        
        mt5_bridges.append(bridge)
        copy_engine.register_bridge(PlatformType.MT5, bridge)
        
        settings.slaves = settings.slaves or []
        settings.slaves.append(AccountConfig(
            platform="mt5",
            login=account.login,
            server=account.server,
            password=account.password
        ))
        save_settings(settings)
        
        return {"status": "added", "platform": "mt5", "login": account.login}
    
    elif account.platform == "ctrader":
        if not account.access_token or not account.account_id:
            raise HTTPException(status_code=400, detail="Access token and account ID required")
        
        bridge = CToderBridge()
        
        if account.refresh_token:
            bridge.set_tokens(account.access_token, account.refresh_token)
        else:
            success = bridge.authenticate(access_token=account.access_token)
            if not success:
                raise HTTPException(status_code=400, detail="cTrader auth failed")
        
        bridge.set_account(account.account_id)
        ctrader_bridges.append(bridge)
        copy_engine.register_bridge(PlatformType.CTRADER, bridge)
        
        settings.slaves = settings.slaves or []
        settings.slaves.append(AccountConfig(
            platform="ctrader",
            login=account.account_id,
            account_id=account.account_id,
            access_token=account.access_token,
            refresh_token=account.refresh_token
        ))
        save_settings(settings)
        
        return {"status": "added", "platform": "ctrader", "account_id": account.account_id}
    
    raise HTTPException(status_code=400, detail="Unsupported platform")


@app.post("/api/start")
async def start_copying():
    global monitor_task
    
    if not settings or not settings.master:
        raise HTTPException(status_code=400, detail="No master configured")
    
    master_platform = PlatformType.MT5 if settings.master.platform == "mt5" else PlatformType.CTRADER
    
    config = CopyConfig(
        master_platform=master_platform,
        slave_platforms=[PlatformType.MT5, PlatformType.CTRADER],
        lot_multiplier=settings.lot_multiplier,
        max_lot=settings.max_lot,
        min_lot=settings.min_lot,
        reverse_trades=settings.reverse_trades,
        copy_sl=settings.copy_sl,
        copy_tp=settings.copy_tp,
        symbol_map=settings.symbol_map
    )
    
    copy_engine.set_config(config)
    await copy_engine.start()
    
    master_bridge = copy_engine.bridges.get(master_platform)
    if master_bridge:
        from core.copy_engine import PositionMonitor
        monitor = PositionMonitor(master_bridge, copy_engine)
        monitor_task = asyncio.create_task(monitor.start(0.5))
    
    return {"status": "started"}


@app.post("/api/stop")
async def stop_copying():
    global monitor_task
    
    if monitor_task:
        monitor_task.cancel()
        monitor_task = None
    
    await copy_engine.stop()
    return {"status": "stopped"}


@app.get("/api/positions")
async def get_positions():
    if not copy_engine.running:
        return {"master": [], "slaves": []}
    
    return copy_engine.sync_positions()


@app.get("/api/account")
async def get_account_info():
    if not settings or not settings.master:
        return None
    
    platform = settings.master.platform
    bridge = copy_engine.bridges.get(
        PlatformType.MT5 if platform == "mt5" else PlatformType.CTRADER
    )
    
    if not bridge:
        return None
    
    return bridge.get_account_info()


@app.get("/api/version")
async def version():
    return {"version": "1.0.0", "name": "CopyTrade Pro"}


@app.get("/api/ctrader/accounts")
async def get_ctrader_accounts(token: str):
    """Fetch cTrader accounts using access token"""
    bridge = CToderBridge()
    bridge.authenticate(access_token=token)
    
    result = bridge._request("GET", "/api/v3/accounts")
    bridge.close()
    
    if not result or "accounts" not in result:
        return {"accounts": []}
    
    accounts = []
    for acc in result["accounts"]:
        if not acc.get("deleted"):
            accounts.append({
                "accountId": acc.get("accountId"),
                "accountNumber": acc.get("accountNumber"),
                "brokerName": acc.get("brokerName"),
                "depositCurrency": acc.get("depositCurrency"),
                "balance": acc.get("balance"),
                "leverage": acc.get("leverage"),
                "live": acc.get("live"),
                "accountStatus": acc.get("accountStatus")
            })
    
    return {"accounts": accounts}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)