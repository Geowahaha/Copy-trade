import MetaTrader5 as mt5
import time
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from enum import Enum


class OrderType(Enum):
    MARKET = 0
    LIMIT = 1
    STOP = 2


class OrderSide(Enum):
    BUY = 0
    SELL = 1


@dataclass
class MT5Connection:
    login: int
    server: str
    password: str
    connected: bool = False


class MT5Bridge:
    def __init__(self):
        self.connected = False
        self.account_info = None
        self.login = None
    
    def connect(self, login: int, server: str, password: str) -> bool:
        if not mt5.initialize():
            error = mt5.last_error()
            print(f"MT5 Init Failed: {error}")
            return False
        
        if not mt5.login(login, password=password, server=server):
            error = mt5.last_error()
            print(f"MT5 Login Failed: {error}")
            mt5.shutdown()
            return False
        
        self.connected = True
        self.account_info = mt5.account_info()
        self.login = login
        print(f"MT5 Connected: Login={login}, Server={server}")
        return True
    
    def disconnect(self):
        if self.connected:
            mt5.shutdown()
            self.connected = False
            self.account_info = None
    
    def get_account_info(self) -> Optional[Dict[str, Any]]:
        if not self.connected:
            return None
        info = mt5.account_info()
        if info is None:
            return None
        return {
            "login": info.login,
            "balance": info.balance,
            "equity": info.equity,
            "margin": info.margin,
            "free_margin": info.margin_free,
            "profit": info.profit,
            "leverage": info.leverage,
            "server": info.server,
            "currency": info.currency
        }
    
    def get_positions(self, symbol: str = None) -> List[Dict[str, Any]]:
        if not self.connected:
            return []
        
        if symbol:
            positions = mt5.positions_get(symbol=symbol)
        else:
            positions = mt5.positions_get()
        
        if positions is None:
            return []
        
        result = []
        for pos in positions:
            result.append({
                "ticket": pos.ticket,
                "symbol": pos.symbol,
                "type": "BUY" if pos.type == 0 else "SELL",
                "volume": pos.volume,
                "price_open": pos.price_open,
                "price_current": pos.price_current,
                "profit": pos.profit,
                "sl": pos.sl,
                "tp": pos.tp,
                "magic": pos.magic,
                "time": pos.time,
                "comment": pos.comment
            })
        return result
    
    def place_order(
        self,
        symbol: str,
        side: str,
        volume: float,
        order_type: str = "MARKET",
        price: float = 0,
        sl: float = 0,
        tp: float = 0,
        comment: str = "",
        magic: int = 0
    ) -> Optional[Dict[str, Any]]:
        if not self.connected:
            return {"retcode": -1, "error": "Not connected"}
        
        side_val = mt5.ORDER_TYPE_BUY if side.upper() == "BUY" else mt5.ORDER_TYPE_SELL
        
        if order_type.upper() == "MARKET":
            order_type_val = side_val
        elif order_type.upper() == "LIMIT":
            order_type_val = mt5.ORDER_TYPE_BUY_LIMIT if side.upper() == "BUY" else mt5.ORDER_TYPE_SELL_LIMIT
        elif order_type.upper() == "STOP":
            order_type_val = mt5.ORDER_TYPE_BUY_STOP if side.upper() == "BUY" else mt5.ORDER_TYPE_SELL_STOP
        else:
            return {"retcode": -1, "error": "Invalid order type"}
        
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            return {"retcode": -1, "error": f"Symbol {symbol} not found"}
        
        if not symbol_info.visible:
            mt5.symbol_select(symbol, True)
        
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": order_type_val,
            "price": price if price > 0 else symbol_info.ask,
            "sl": sl,
            "tp": tp,
            "deviation": 20,
            "magic": magic,
            "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC
        }
        
        result = mt5.order_send(request)
        
        if result is None:
            return {"retcode": -1, "error": "Order send failed"}
        
        return {
            "retcode": result.retcode,
            "order_id": result.order,
            "deal_id": result.deal,
            "comment": result.comment
        }
    
    def close_position(self, ticket: int, volume: float = None, comment: str = "") -> Optional[Dict[str, Any]]:
        if not self.connected:
            return {"retcode": -1, "error": "Not connected"}
        
        positions = mt5.positions_get(ticket=ticket)
        if not positions:
            return {"retcode": -1, "error": "Position not found"}
        
        pos = positions[0]
        close_volume = volume if volume else pos.volume
        
        side = mt5.ORDER_TYPE_SELL if pos.type == 0 else mt5.ORDER_TYPE_BUY
        
        symbol_info = mt5.symbol_info(pos.symbol)
        if symbol_info is None:
            return {"retcode": -1, "error": "Symbol not found"}
        
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": pos.symbol,
            "volume": close_volume,
            "type": side,
            "position": ticket,
            "price": symbol_info.bid if pos.type == 0 else symbol_info.ask,
            "deviation": 20,
            "comment": comment or f"Close #{ticket}",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC
        }
        
        result = mt5.order_send(request)
        
        if result is None:
            return {"retcode": -1, "error": "Order send failed"}
        
        return {
            "retcode": result.retcode,
            "order_id": result.order,
            "deal_id": result.deal
        }
    
    def modify_position(self, ticket: int, sl: float, tp: float) -> Optional[Dict[str, Any]]:
        if not self.connected:
            return {"retcode": -1, "error": "Not connected"}
        
        positions = mt5.positions_get(ticket=ticket)
        if not positions:
            return {"retcode": -1, "error": "Position not found"}
        
        pos = positions[0]
        
        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "symbol": pos.symbol,
            "volume": pos.volume,
            "position": ticket,
            "sl": sl,
            "tp": tp
        }
        
        result = mt5.order_send(request)
        
        if result is None:
            return {"retcode": -1, "error": "Order modify failed"}
        
        return {
            "retcode": result.retcode,
            "order_id": result.order
        }
    
    def get_symbol_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        if not self.connected:
            return None
        
        info = mt5.symbol_info(symbol)
        if info is None:
            return None
        
        return {
            "symbol": info.name,
            "bid": info.bid,
            "ask": info.ask,
            "last": info.last,
            "volume": info.volume,
            "digits": info.digits,
            "point": info.point,
            "trade_mode": info.trade_mode,
            "spread": info.spread
        }
    
    def get_symbols(self) -> List[str]:
        if not self.connected:
            return []
        
        symbols = mt5.symbols_get()
        if symbols is None:
            return []
        
        return [s.name for s in symbols]
    
    def wait_for_tick(self, symbol: str, timeout: int = 5000):
        return mt5.symbol_info_tick(symbol)