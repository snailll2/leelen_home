class DeviceStatusEvent:
    function_id: int = 0
    logic_address: int = 0
    state: bytes = bytes()  # 对应 byte[]，用 List[int] 表示每个 byte

