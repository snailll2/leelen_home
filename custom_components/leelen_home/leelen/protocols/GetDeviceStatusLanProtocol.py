import threading
from typing import Optional, ClassVar

from ..protocols.BaseLanProtocol import BaseLanProtocol
from ..common import LanProtocolCmd


class GetDeviceStatusLanProtocol(BaseLanProtocol):
    _instance: ClassVar[Optional['GetDeviceStatusLanProtocol']] = None
    _lock = threading.Lock()  # For thread-safe singleton

    def __init__(self):
        if GetDeviceStatusLanProtocol._instance is not None:
            raise RuntimeError("Use GetDeviceStatusLanProtocol.instance() to get the instance")

        super().__init__()
        self.cmd = LanProtocolCmd.GET_DEVICE_STATUS
        self.payload_type = bytes([0])
        self._device_address: Optional[bytes] = None

    @classmethod
    def get_instance(cls) -> 'GetDeviceStatusLanProtocol':
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def build_body(self) -> bool:
        if self._device_address is not None:
            self.request_data_body = self._device_address
        return True

    @property
    def device_address(self) -> Optional[bytes]:
        return self._device_address

    @device_address.setter
    def device_address(self, value: bytes) -> None:
        self._device_address = value

    def set_device_address(self, address: bytes) -> None:
        """Alternative method to set device address (Java-style)"""
        self._device_address = address
