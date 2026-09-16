from typing import Optional

from ..protocols.BaseLanProtocol import BaseLanProtocol
from ..common import LanProtocolCmd


class GetDeviceStatusLanProtocol(BaseLanProtocol):

    def __init__(self):
        super().__init__()
        self.cmd = LanProtocolCmd.GET_DEVICE_STATUS
        self.payload_type = bytes([0])
        self._device_address: Optional[bytes] = None

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
