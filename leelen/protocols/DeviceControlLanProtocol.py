import threading
import logging

from ..protocols.BaseLanProtocol import BaseLanProtocol
from ..common import LanProtocolCmd


class DeviceControlLanProtocol(BaseLanProtocol):
    _instance = None
    _lock = threading.Lock()
    
    def __init__(self):
        super().__init__()
        self.cmd = LanProtocolCmd.DEV_CTRL
        self.payload_type = bytes([0])
        self.service_address = None
        self.tlv_data = None
        self.TAG = "DeviceControlLanProtocol"

    @classmethod
    def get_instance(cls) -> 'DeviceControlLanProtocol':
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = DeviceControlLanProtocol()
        return cls._instance

    def build_body(self) -> bool:
        with self._lock:
            if self.tlv_data is not None and self.service_address is not None:
                n = len(self.tlv_data)
                by = n & 0xff
                by2 = (n + 3) & 0xff
                
                buffer = bytearray()
                buffer.extend(bytes([by2]))
                buffer.extend(self.service_address)
                buffer.extend(bytes([by]))
                buffer.extend(self.tlv_data)
                
                self.request_data_body = bytes(buffer)
                return True
                
            logging.error(f"{self.TAG}: tlvData or mServiceAddress is null.")
            return False

    def set_encode_tlv_info(self, data: bytes) -> None:
        self.tlv_data = data

    def set_service_address(self, address: bytes) -> None:
        self.service_address = address
