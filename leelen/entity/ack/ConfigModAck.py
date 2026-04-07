from dataclasses import dataclass, field
from typing import List

from .ModInfo import ModInfo


@dataclass
class ConfigModAck:
    T1: int = 0
    T2: int = 0
    config_struct_version: int = 0
    config_version: int = 0
    mod_info: List[ModInfo] = field(default_factory=list)
    msg: str = ""
    ack: int = 0  # 继承自 BaseAck，假设 BaseAck 有 ack 字段

    @staticmethod
    def from_dict(data: dict) -> "ConfigModAck":
        mod_info_data = data.get("mod_info", [])
        mod_info_list = [ModInfo.from_dict(item) for item in mod_info_data] if isinstance(mod_info_data, list) else []
        return ConfigModAck(
            T1=data.get("T1", 0),
            T2=data.get("T2", 0),
            config_struct_version=data.get("config_struct_version", 0),
            config_version=data.get("config_version", 0),
            mod_info=mod_info_list,
            msg=data.get("msg", ""),
            ack=data.get("ack", 0)
        )

    def to_dict(self) -> dict:
        return {
            "T1": self.T1,
            "T2": self.T2,
            "config_struct_version": self.config_struct_version,
            "config_version": self.config_version,
            "mod_info": [m.to_dict() for m in self.mod_info],
            "msg": self.msg,
            "ack": self.ack
        }
