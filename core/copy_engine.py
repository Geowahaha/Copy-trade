"""
Copy Trade Engine - Real-time trade copying between platforms
"""
import asyncio
import time
import uuid
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
from collections import deque
import threading
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PlatformType(Enum):
    MT5 = "mt5"
    CTRADER = "ctrader"


class TradeAction(Enum):
    OPEN = "open"
    CLOSE = "close"
    MODIFY = "modify"


@dataclass
class TradeSignal:
    id: str
    symbol: str
    side: str
    volume: float
    action: TradeAction
    platform: PlatformType
    price: float = 0
    sl: float = 0
    tp: float = 0
    master_ticket: str = ""
    order_type: str = "MARKET"
    timestamp: float = field(default_factory=time.time)


@dataclass
class CopyConfig:
    master_platform: PlatformType
    slave_platforms: List[PlatformType]
    lot_multiplier: float = 1.0
    max_lot: float = 100.0
    min_lot: float = 0.01
    reverse_trades: bool = False
    copy_sl: bool = True
    copy_tp: bool = True
    symbol_map: Dict[str, str] = field(default_factory=dict)


@dataclass  
class Position:
    ticket: str
    master_ticket: str
    symbol: str
    side: str
    volume: float
    open_price: float
    platform: PlatformType
    created_at: float = field(default_factory=time.time)


class CopyEngine:
    def __init__(self):
        self.bridges: Dict[PlatformType, Any] = {}
        self.config = None
        self.positions: Dict[str, Position] = {}
        self.pending_signals: asyncio.Queue = asyncio.Queue()
        self.running = False
        self._callbacks: List[Callable] = []
        self._latency_log = deque(maxlen=100)
        self._lock = threading.Lock()
        self._task: Optional[asyncio.Task] = None
    
    def register_bridge(self, platform: PlatformType, bridge: Any):
        self.bridges[platform] = bridge
        logger.info(f"Registered bridge for {platform.value}")
    
    def set_config(self, config: CopyConfig):
        self.config = config
    
    def add_callback(self, callback: Callable):
        self._callbacks.append(callback)
    
    def map_symbol(self, symbol: str) -> str:
        if self.config and symbol in self.config.symbol_map:
            return self.config.symbol_map[symbol]
        return symbol
    
    def calculate_lot(self, master_volume: float) -> float:
        if not self.config:
            return master_volume
        
        lot = master_volume * self.config.lot_multiplier
        lot = max(self.config.min_lot, min(lot, self.config.max_lot))
        return round(lot, 2)
    
    def process_signal(self, signal: TradeSignal) -> List[Dict[str, Any]]:
        results = []
        start_time = time.time()
        
        for slave_platform in self.config.slave_platforms:
            bridge = self.bridges.get(slave_platform)
            if not bridge:
                continue
            
            try:
                mapped_symbol = self.map_symbol(signal.symbol)
                
                if signal.action == TradeAction.OPEN:
                    side = signal.side
                    if self.config.reverse_trades:
                        side = "SELL" if side == "BUY" else "BUY"
                    
                    if slave_platform == PlatformType.MT5:
                        result = bridge.place_order(
                            symbol=mapped_symbol,
                            side=side,
                            volume=signal.volume,
                            order_type=signal.order_type,
                            price=signal.price,
                            sl=signal.sl if self.config.copy_sl else 0,
                            tp=signal.tp if self.config.copy_tp else 0,
                            magic=0,
                            comment=f"COPY_{signal.master_ticket}"
                        )
                    else:
                        result = bridge.place_order(
                            symbol=mapped_symbol,
                            side=side,
                            volume=signal.volume,
                            order_type=signal.order_type,
                            price=signal.price,
                            stop_loss=signal.sl if self.config.copy_sl else 0,
                            take_profit=signal.tp if self.config.copy_tp else 0,
                            client_id=signal.id
                        )
                    
                    if result and result.get("retcode", result.get("order_id")):
                        position = Position(
                            ticket=result.get("order_id", str(uuid.uuid4())),
                            master_ticket=signal.master_ticket,
                            symbol=mapped_symbol,
                            side=side,
                            volume=signal.volume,
                            open_price=signal.price,
                            platform=slave_platform
                        )
                        with self._lock:
                            self.positions[position.ticket] = position
                        
                        results.append({
                            "platform": slave_platform.value,
                            "ticket": position.ticket,
                            "status": "success"
                        })
                
                elif signal.action == TradeAction.CLOSE:
                    if slave_platform == PlatformType.MT5:
                        result = bridge.close_position(
                            ticket=signal.master_ticket,
                            volume=signal.volume
                        )
                    else:
                        result = bridge.close_position(
                            position_id=signal.master_ticket,
                            volume=signal.volume
                        )
                    
                    if result and result.get("retcode", 0) >= 0:
                        with self._lock:
                            to_remove = [k for k, v in self.positions.items() 
                                        if v.master_ticket == signal.master_ticket]
                            for k in to_remove:
                                del self.positions[k]
                        
                        results.append({
                            "platform": slave_platform.value,
                            "status": "closed"
                        })
                
            except Exception as e:
                logger.error(f"Error processing signal on {slave_platform.value}: {e}")
                results.append({
                    "platform": slave_platform.value,
                    "status": "error",
                    "error": str(e)
                })
        
        latency = (time.time() - start_time) * 1000
        self._latency_log.append(latency)
        
        for callback in self._callbacks:
            try:
                callback(signal, results, latency)
            except Exception as e:
                logger.error(f"Callback error: {e}")
        
        return results
    
    async def start(self):
        self.running = True
        self._task = asyncio.create_task(self._process_loop())
        logger.info("Copy Engine started")
    
    async def stop(self):
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Copy Engine stopped")
    
    async def _process_loop(self):
        while self.running:
            try:
                signal = await asyncio.wait_for(
                    self.pending_signals.get(), 
                    timeout=0.1
                )
                self.process_signal(signal)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Process loop error: {e}")
    
    def submit_signal(self, signal: TradeSignal):
        if self.running:
            self.pending_signals.put_nowait(signal)
    
    def get_latency_stats(self) -> Dict[str, float]:
        if not self._latency_log:
            return {"avg": 0, "min": 0, "max": 0, "recent": 0}
        
        log = list(self._latency_log)
        return {
            "avg": sum(log) / len(log),
            "min": min(log),
            "max": max(log),
            "recent": log[-1]
        }
    
    def sync_positions(self) -> Dict[str, List]:
        master_positions = []
        slave_positions = []
        
        master_bridge = self.bridges.get(self.config.master_platform)
        if master_bridge:
            master_positions = master_bridge.get_positions() or []
        
        for platform, bridge in self.bridges.items():
            if platform == self.config.master_platform:
                continue
            positions = bridge.get_positions() or []
            for pos in positions:
                pos["platform"] = platform.value
            slave_positions.extend(positions)
        
        return {
            "master": master_positions,
            "slaves": slave_positions
        }
    
    def get_stats(self) -> Dict[str, Any]:
        return {
            "active_positions": len(self.positions),
            "pending_signals": self.pending_signals.qsize(),
            "latency": self.get_latency_stats()
        }


class PositionMonitor:
    def __init__(self, master_bridge: Any, copy_engine: CopyEngine):
        self.master_bridge = master_bridge
        self.copy_engine = copy_engine
        self.last_positions: Dict = {}
        self._running = False
        self._task: Optional[asyncio.Task] = None
    
    async def start(self, interval: float = 0.5):
        self._running = True
        self._task = asyncio.create_task(self._monitor_loop(interval))
        logger.info("Position Monitor started")
    
    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Position Monitor stopped")
    
    async def _monitor_loop(self, interval: float):
        while self._running:
            try:
                await asyncio.sleep(interval)
                positions = self.master_bridge.get_positions() or []
                
                current_tickets = {str(p.get("ticket")): p for p in positions}
                last_tickets = set(self.last_positions.keys())
                current_ticket_set = set(current_tickets.keys())
                
                new_positions = current_ticket_set - last_tickets
                closed_positions = last_tickets - current_ticket_set
                
                master_platform = self.copy_engine.config.master_platform if self.copy_engine.config else PlatformType.MT5
                
                for ticket in new_positions:
                    pos = current_tickets[ticket]
                    signal = TradeSignal(
                        id=str(uuid.uuid4()),
                        symbol=pos["symbol"],
                        side=pos["type"],
                        volume=pos["volume"],
                        action=TradeAction.OPEN,
                        platform=master_platform,
                        price=pos["price_open"],
                        sl=pos.get("sl", 0),
                        tp=pos.get("tp", 0),
                        master_ticket=str(ticket)
                    )
                    self.copy_engine.submit_signal(signal)
                
                for ticket in closed_positions:
                    pos = self.last_positions[ticket]
                    signal = TradeSignal(
                        id=str(uuid.uuid4()),
                        symbol=pos["symbol"],
                        side=pos["type"],
                        volume=pos["volume"],
                        action=TradeAction.CLOSE,
                        platform=master_platform,
                        master_ticket=str(ticket)
                    )
                    self.copy_engine.submit_signal(signal)
                
                self.last_positions = current_tickets
                
            except Exception as e:
                logger.error(f"Monitor loop error: {e}")
    
    def get_current_positions(self) -> List[Dict]:
        return list(self.last_positions.values())