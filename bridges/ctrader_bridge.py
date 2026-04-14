"""
cTrader OpenAPI Bridge
Uses WebSocket/TCP connection to cTrader servers
Documentation: https://help.ctrader.com/open-api/connection/
"""
import socket
import json
import time
import uuid
import threading
from typing import Optional, Dict, Any, List


CT_HOST_DEMO = "demo1.p.ctrader.com"
CT_HOST_LIVE = "live1.p.ctrader.com"
CT_PORT_JSON = 5036  # WebSocket for JSON


class CToderBridge:
    def __init__(self, app_id: str = None, app_secret: str = None):
        self.app_id = app_id
        self.app_secret = app_secret
        self.access_token = None
        self.refresh_token = None
        self.token_expires = 0
        self.account_id = None
        self._socket = None
        self._connected = False
        self._session_id = ""
        self._msg_id = 0
        self._lock = threading.Lock()
        self._responses = {}
        self._demo = False
    
    def connect(self, is_demo: bool = False) -> bool:
        host = CT_HOST_DEMO if is_demo else CT_HOST_LIVE
        self._demo = is_demo
        
        try:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._socket.settimeout(30)
            self._socket.connect((host, CT_PORT_JSON))
            self._connected = True
            print(f"Connected to cTrader {host}:{CT_PORT_JSON}")
            return True
        except Exception as e:
            print(f"Connection failed: {e}")
            self._connected = False
            return False
    
    def authenticate(self, access_token: str = None, refresh_token: str = None) -> bool:
        if access_token:
            self.access_token = access_token
        if refresh_token:
            self.refresh_token = refresh_token
        return bool(self.access_token)
    
    def set_tokens(self, access_token: str, refresh_token: str):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.token_expires = int(time.time()) + 3500
    
    def set_account(self, account_id: str):
        self.account_id = account_id
    
    def _send_json(self, payload: Dict) -> Optional[Dict]:
        if not self._connected:
            return None
        
        client_msg_id = str(uuid.uuid4())[:8]
        payload["clientMsgId"] = client_msg_id
        
        try:
            msg = json.dumps(payload) + "\n"
            self._socket.sendall(msg.encode())
            
            start = time.time()
            while time.time() - start < 10:
                try:
                    self._socket.settimeout(1)
                    response = self._socket.recv(4096)
                    if response:
                        data = json.loads(response.decode())
                        if data.get("clientMsgId") == client_msg_id:
                            return data
                except socket.timeout:
                    continue
            
            return None
        except Exception as e:
            print(f"Send error: {e}")
            return None
    
    def application_auth(self) -> bool:
        if not self.app_id or not self.app_secret:
            return False
        
        auth_req = {
            "payloadType": 2100,
            "payload": {
                "clientId": self.app_id,
                "clientSecret": self.app_secret
            }
        }
        
        result = self._send_json(auth_req)
        if result:
            self._session_id = result.get("payload", {}).get("sessionId", "")
            return bool(self._session_id)
        return False
    
    def access_token_auth(self, access_token: str) -> bool:
        auth_req = {
            "payloadType": 2101,
            "payload": {
                "accessToken": access_token
            }
        }
        
        result = self._send_json(auth_req)
        if result:
            payload = result.get("payload", {})
            if payload.get("resultStatus") == 0:
                self.access_token = access_token
                return True
        return False
    
    def refresh_access_token(self) -> bool:
        if not self.refresh_token or not self.app_id or not self.app_secret:
            return False
        
        refresh_req = {
            "payloadType": 2102,
            "payload": {
                "clientId": self.app_id,
                "clientSecret": self.app_secret,
                "refreshToken": self.refresh_token
            }
        }
        
        result = self._send_json(refresh_req)
        if result:
            payload = result.get("payload", {})
            if payload.get("resultStatus") == 0:
                self.access_token = payload.get("accessToken", "")
                self.refresh_token = payload.get("refreshToken", self.refresh_token)
                self.token_expires = int(time.time()) + payload.get("expiresIn", 3500)
                return True
        return False
    
    def account_auth(self, account_id: str) -> bool:
        if not self._session_id and not self.access_token:
            return False
        
        auth_req = {
            "payloadType": 2103,
            "payload": {
                "sessionId": self._session_id,
                "accessToken": self.access_token,
                "accountId": int(account_id)
            }
        }
        
        result = self._send_json(auth_req)
        if result:
            payload = result.get("payload", {})
            if payload.get("resultStatus") == 0:
                self.account_id = account_id
                return True
        return False
    
    def get_account_info(self) -> Optional[Dict[str, Any]]:
        if not self.account_id:
            return None
        
        req = {
            "payloadType": 2300,
            "payload": {
                "accountId": int(self.account_id)
            }
        }
        
        result = self._send_json(req)
        if not result:
            return None
        
        payload = result.get("payload", {})
        return {
            "balance": payload.get("balance", 0),
            "equity": payload.get("equity", 0),
            "profit": payload.get("profit", 0),
            "margin": payload.get("margin", 0),
            "free_margin": payload.get("marginFree", 0),
            "currency": payload.get("currency", "")
        }
    
    def get_positions(self) -> List[Dict[str, Any]]:
        if not self.account_id:
            return []
        
        req = {
            "payloadType": 2313,
            "payload": {
                "accountId": int(self.account_id)
            }
        }
        
        result = self._send_json(req)
        if not result:
            return []
        
        positions = []
        for pos in result.get("payload", {}).get("positions", []):
            positions.append({
                "positionId": pos.get("positionId"),
                "symbol": pos.get("symbol"),
                "side": "BUY" if pos.get("buyQty", 0) > 0 else "SELL",
                "volume": pos.get("buyQty", 0) or pos.get("sellQty", 0),
                "entry_price": pos.get("avgOpenPrice"),
                "profit": pos.get("profitLoss"),
                "stop_loss": pos.get("stopLoss"),
                "take_profit": pos.get("takeProfit")
            })
        return positions
    
    def place_order(
        self,
        symbol: str,
        side: str,
        volume: float,
        order_type: str = "MARKET",
        price: float = 0,
        stop_loss: float = 0,
        take_profit: float = 0,
        client_id: str = ""
    ) -> Optional[Dict[str, Any]]:
        if not self.account_id:
            return {"error": "No account selected"}
        
        side_val = 1 if side.upper() == "BUY" else -1
        order_type_val = 1 if order_type.upper() == "MARKET" else 2
        
        order_req = {
            "payloadType": 2350,
            "payload": {
                "accountId": int(self.account_id),
                "symbol": symbol,
                "side": side_val,
                "quantity": int(volume * 100000),
                "type": order_type_val,
                "stopLoss": int(stop_loss * 100000) if stop_loss else 0,
                "takeProfit": int(take_profit * 100000) if take_profit else 0
            }
        }
        
        if order_type.upper() != "MARKET" and price > 0:
            order_req["payload"]["price"] = int(price * 100000)
        
        result = self._send_json(order_req)
        if not result:
            return {"error": "Order failed"}
        
        payload = result.get("payload", {})
        return {
            "order_id": payload.get("orderId"),
            "status": "success" if payload.get("resultStatus") == 0 else "error"
        }
    
    def close_position(self, position_id: str, volume: float = None) -> Optional[Dict[str, Any]]:
        if not self.account_id:
            return {"error": "No account selected"}
        
        close_req = {
            "payloadType": 2351,
            "payload": {
                "accountId": int(self.account_id),
                "positionId": int(position_id)
            }
        }
        
        if volume:
            close_req["payload"]["quantity"] = int(volume * 100000)
        
        result = self._send_json(close_req)
        if not result:
            return {"error": "Close failed"}
        
        return {"status": "closed"}
    
    def close(self):
        if self._socket:
            try:
                self._socket.close()
            except:
                pass
        self._connected = False


class CToderRESTBridge:
    """Fallback REST bridge for HTTP endpoints"""
    
    def __init__(self, app_id: str = None, app_secret: str = None):
        self.app_id = app_id
        self.app_secret = app_secret
        self.access_token = None
        self.refresh_token = None
        self.account_id = None
        self.base_url = "https://api.ctrader.com/go_api"
    
    def authenticate(self, access_token: str = None) -> bool:
        if access_token:
            self.access_token = access_token
            return True
        return False
    
    def set_account(self, account_id: str):
        self.account_id = account_id
    
    def get_account_info(self) -> Optional[Dict]:
        return None
    
    def get_positions(self) -> List[Dict]:
        return []
    
    def place_order(self, symbol: str, side: str, volume: float, **kwargs) -> Optional[Dict]:
        return None
    
    def close_position(self, position_id: str, volume: float = None) -> Optional[Dict]:
        return None
    
    def close(self):
        pass