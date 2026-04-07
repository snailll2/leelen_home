from dataclasses import dataclass, field
from typing import Optional

from .BaseDaoBean import BaseDaoBean


@dataclass
class LogicServer(BaseDaoBean):
    logic_addr: int = 0
    dev_addr: int = 0
    srv_id: int = 0
    srv_type: int = 0
    storage_type: int = 0
    logic_type: int = 0
    func_grp_num: int = 0
    func_grp_id: Optional[bytes] = field(default_factory=bytes)
    display: int = 0
    icon_id: int = 0
    logic_name: str = ""
    room_id: int = 0

    # 字段名常量（用于字段映射）
    LOGIC_ADDR = "logic_addr"
    DEV_ADDR = "dev_addr"
    SRV_ID = "srv_id"
    SRV_TYPE = "srv_type"
    STORAGE_TYPE = "storage_type"
    LOGIC_TYPE = "logic_type"
    FUNC_GRP_NUM = "func_grp_num"
    FUNC_GRP_ID = "func_grp_id"
    DISPLAY = "display"
    ICON_ID = "icon_id"
    LOGIC_NAME = "logic_name"
    ROOM_ID = "room_id"
