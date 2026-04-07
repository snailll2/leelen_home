from dataclasses import dataclass


@dataclass
class BaseDaoBean:
    id: int = 0
    create_time: int = 0  # long in Java → int in Python（通常够用）
    update_time: int = 0
    gateway_address: str = ""

    # 字段名常量，可用于字段映射
    CREATE_TIME = "create_time"
    UPDATE_TIME = "update_time"
    GATEWAY_ADDRESS = "gateway_address"
