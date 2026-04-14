"""
cTrader OpenAPI Bridge
Documentation: https://cdn.ctrader.com/go-api-samples/openapi-config.json
"""
import requests
import time
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
import threading


BASE_URL = "https://api.ctrader.com/go_api"


class CToderBridge:
    def __init__(self, app_id: str = None, app_secret: str = None):
        self.app_id = app_id
        self.app_secret = app_secret
        self.access_token = None
        self.refresh_token = None
        self.token_expires = 0
        self.account_id = None
        self.base_url = BASE_URL
        self._session = requests.Session()
        self._session.headers.update({
            "Content-Type": "application/json",
            "Accept": "application/json"
        })
    
    def authenticate(self, access_token: str = None, refresh_token: str = None) -> bool:
        if access_token:
            self.access_token = access_token
            self._session.headers["Authorization"] = f"Bearer {access_token}"
            return True
        if refresh_token:
            self.refresh_token = refresh_token
            return True
        return False
    
    def set_tokens(self, access_token: str, refresh_token: str):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.token_expires = int(time.time()) + 3500
        self._session.headers["Authorization"] = f"Bearer {access_token}"
    
    def _check_token_expired(self) -> bool:
        if not self.access_token:
            return True
        if self.token_expires and time.time() > self.token_expires - 300:
            return True
        return False
    
    def refresh_access_token(self) -> bool:
        if not self.refresh_token or not self.app_id or not self.app_secret:
            print("Cannot refresh: missing refresh_token or app credentials")
            return False
        
        data = {
            "grant_type": "refresh_token",
            "client_id": self.app_id,
            "client_secret": self.app_secret,
            "refresh_token": self.refresh_token
        }
        
        result = self._request("POST", "/oauth/token", data=data)
        if not result:
            return False
        
        self.access_token = result.get("access_token")
        self.refresh_token = result.get("refresh_token", self.refresh_token)
        self.token_expires = int(time.time()) + result.get("expires_in", 3500)
        self._session.headers["Authorization"] = f"Bearer {self.access_token}"
        
        print(f"Token refreshed, expires in {result.get('expires_in')}s")
        return True
    
    def _ensure_valid_token(self) -> bool:
        if self._check_token_expired() and self.refresh_token:
            return self.refresh_access_token()
        return bool(self.access_token)
    
    def set_account(self, account_id: str):
        self.account_id = account_id
    
    def _request(self, method: str, endpoint: str, data: dict = None, params: dict = None) -> Optional[Dict]:
        self._ensure_valid_token()
        
        url = f"{self.base_url}{endpoint}"
        try:
            response = self._session.request(method, url, json=data, params=params, timeout=10)
            
            if response.status_code == 401:
                if self.refresh_access_token():
                    response = self._session.request(method, url, json=data, params=params, timeout=10)
                else:
                    return None
            
            response.raise_for_status()
            return response.json() if response.content else {}
        except requests.RequestException as e:
            print(f"cTrader API Error: {e}")
            return None
    
    def get_account_info(self) -> Optional[Dict[str, Any]]:
        if not self.account_id:
            return None
        
        result = self._request("GET", f"/api/v3/accounts/{self.account_id}")
        if not result:
            return None
        
        return {
            "account_id": result.get("accountId"),
            "balance": result.get("balance"),
            "equity": result.get("equity"),
            "margin": result.get("margin"),
            "free_margin": result.get("freeMargin"),
            "profit": result.get("profit"),
            "currency": result.get("currency")
        }
    
    def get_positions(self) -> List[Dict[str, Any]]:
        if not self.account_id:
            return []
        
        result = self._request("GET", f"/api/v3/positions/{self.account_id}")
        if not result or "positions" not in result:
            return []
        
        positions = []
        for pos in result["positions"]:
            positions.append({
                "id": pos.get("positionId"),
                "symbol": pos.get("symbol"),
                "side": "BUY" if pos.get("buyQty", 0) > 0 else "SELL",
                "volume": pos.get("buyQty", 0) or pos.get("sellQty", 0),
                "entry_price": pos.get("avgOpenPrice"),
                "current_price": pos.get("avgOpenPrice"),
                "profit": pos.get("profitLoss"),
                "stop_loss": pos.get("stopLoss"),
                "take_profit": pos.get("takeProfit"),
                "open_time": pos.get("openTime")
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
        
        side_map = {"BUY": 1, "SELL": -1}
        side_value = side_map.get(side.upper(), 1)
        
        order = {
            "accountId": self.account_id,
            "symbol": symbol,
            "quantity": volume,
            "side": side_value,
            "type": 1 if order_type.upper() == "MARKET" else 2,
            "stopLoss": stop_loss,
            "takeProfit": take_profit
        }
        
        if order_type.upper() != "MARKET" and price > 0:
            order["price"] = price
        
        if client_id:
            order["clientId"] = client_id
        
        result = self._request("POST", f"/api/v3/orders/{self.account_id}", data=order)
        if not result:
            return {"error": "Order placement failed"}
        
        return {
            "order_id": result.get("orderId"),
            "status": result.get("status"),
            "client_id": result.get("clientId")
        }
    
    def close_position(self, position_id: str, volume: float = None, client_id: str = "") -> Optional[Dict[str, Any]]:
        if not self.account_id:
            return {"error": "No account selected"}
        
        result = self._request(
            "DELETE", 
            f"/api/v3/positions/{self.account_id}/{position_id}",
            data={"quantity": volume} if volume else {}
        )
        
        if not result:
            return {"error": "Close position failed"}
        
        return {
            "status": result.get("status"),
            "closed_volume": result.get("filledQuantity", 0)
        }
    
    def cancel_order(self, order_id: str) -> bool:
        if not self.account_id:
            return False
        
        result = self._request("DELETE", f"/api/v3/orders/{self.account_id}/{order_id}")
        return result is not None
    
    def get_pending_orders(self) -> List[Dict[str, Any]]:
        if not self.account_id:
            return []
        
        result = self._request("GET", f"/api/v3/orders/{self.account_id}")
        if not result or "orders" not in result:
            return []
        
        orders = []
        for order in result["orders"]:
            orders.append({
                "order_id": order.get("orderId"),
                "symbol": order.get("symbol"),
                "side": "BUY" if order.get("side", 1) > 0 else "SELL",
                "quantity": order.get("quantity"),
                "type": "MARKET" if order.get("type") == 1 else "LIMIT",
                "price": order.get("price"),
                "stop_loss": order.get("stopLoss"),
                "take_profit": order.get("takeProfit"),
                "status": order.get("status"),
                "created_at": order.get("createdAt")
            })
        return orders
    
    def get_symbol_info(self, symbol: str) -> Optional[Dict[str, Any]]:
        result = self._request("GET", f"/api/v3/symbols/{symbol}")
        if not result:
            return None
        
        return {
            "symbol": result.get("symbol"),
            "bid": result.get("bid"),
            "ask": result.get("ask"),
            "digits": result.get("precision"),
            "min_quantity": result.get("minQuantity"),
            "max_quantity": result.get("maxQuantity"),
            "lot_size": result.get("lotSize")
        }
    
    def get_symbols(self) -> List[str]:
        result = self._request("GET", "/api/v3/symbols")
        if not result or "symbols" not in result:
            return []
        
        return [s.get("symbol") for s in result["symbols"]]
    
    def get_oauth_token(self, code: str, redirect_uri: str) -> Optional[Dict]:
        if not self.app_id or not self.app_secret:
            return None
        
        data = {
            "grant_type": "authorization_code",
            "client_id": self.app_id,
            "client_secret": self.app_secret,
            "code": code,
            "redirect_uri": redirect_uri
        }
        
        result = self._request("POST", "/oauth/token", data=data)
        if not result:
            return None
        
        self.access_token = result.get("access_token")
        self.refresh_token = result.get("refresh_token")
        self.token_expires = time.time() + result.get("expires_in", 3600)
        
        return result
    
    def refresh_oauth_token(self) -> bool:
        if not self.refresh_token or not self.app_id or not self.app_secret:
            return False
        
        data = {
            "grant_type": "refresh_token",
            "client_id": self.app_id,
            "client_secret": self.app_secret,
            "refresh_token": self.refresh_token
        }
        
        result = self._request("POST", "/oauth/token", data=data)
        if not result:
            return False
        
        self.access_token = result.get("access_token")
        self.refresh_token = result.get("refresh_token")
        self.token_expires = time.time() + result.get("expires_in", 3600)
        
        return True
    
    def close(self):
        self.access_token = None
        self.refresh_token = None
        self._session.close()