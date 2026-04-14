from dataclasses import dataclass
from typing import Dict, List, Optional
import json
import os


@dataclass
class AccountConfig:
    platform: str
    login: str
    server: str = ""
    password: str = ""
    access_token: str = ""
    account_id: str = ""
    enabled: bool = True
    
    def to_dict(self):
        return {
            "platform": self.platform,
            "login": self.login,
            "server": self.server,
            "enabled": self.enabled
        }
    
    @classmethod
    def from_dict(cls, data: dict):
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class AppSettings:
    master: Optional[AccountConfig] = None
    slaves: List[AccountConfig] = None
    lot_multiplier: float = 1.0
    max_lot: float = 100.0
    min_lot: float = 0.01
    reverse_trades: bool = False
    copy_sl: bool = True
    copy_tp: bool = True
    symbol_map: Dict[str, str] = None
    
    def __post_init__(self):
        if self.slaves is None:
            self.slaves = []
        if self.symbol_map is None:
            self.symbol_map = {}
    
    def save(self, path: str = "config.json"):
        data = {
            "master": self.master.to_dict() if self.master else None,
            "slaves": [s.to_dict() for s in self.slaves],
            "lot_multiplier": self.lot_multiplier,
            "max_lot": self.max_lot,
            "min_lot": self.min_lot,
            "reverse_trades": self.reverse_trades,
            "copy_sl": self.copy_sl,
            "copy_tp": self.copy_tp,
            "symbol_map": self.symbol_map
        }
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)
    
    @classmethod
    def load(cls, path: str = "config.json"):
        if not os.path.exists(path):
            return cls()
        
        with open(path, 'r') as f:
            data = json.load(f)
        
        master = None
        if data.get("master"):
            master = AccountConfig.from_dict(data["master"])
        
        slaves = [AccountConfig.from_dict(s) for s in data.get("slaves", [])]
        
        return cls(
            master=master,
            slaves=slaves,
            lot_multiplier=data.get("lot_multiplier", 1.0),
            max_lot=data.get("max_lot", 100.0),
            min_lot=data.get("min_lot", 0.01),
            reverse_trades=data.get("reverse_trades", False),
            copy_sl=data.get("copy_sl", True),
            copy_tp=data.get("copy_tp", True),
            symbol_map=data.get("symbol_map", {})
        )


def load_settings(path: str = "config.json") -> AppSettings:
    return AppSettings.load(path)


def save_settings(settings: AppSettings, path: str = "config.json"):
    settings.save(path)