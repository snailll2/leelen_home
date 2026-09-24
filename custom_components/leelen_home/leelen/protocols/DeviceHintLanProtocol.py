from typing import Optional

from ..protocols.BaseLanProtocol import BaseLanProtocol
from ..common import LanProtocolCmd
from ..common.LeelenType import DeviceMode


class DeviceHintLanProtocol(BaseLanProtocol):
    """设备定位/闪烁提示指令(cmd DEVICE_HINT = [5, 2])。

    官方 App「设备定位」按下时下发:body = [mode 1B][deviceAddr 2B(小端)],
    mode 取 ``DeviceMode.MODE_FLASH``(bytes([1]),设备指示灯闪烁 30 秒)
    或 ``DeviceMode.MODE_PING``(bytes([0]))。网关据此转发给目标设备让它闪灯,
    不回包或回 ``[isFlash 1B][deviceAddr 2B]`` 状态帧(见 Java handleDeviceHint)。
    """

    def __init__(self):
        super().__init__()
        self.cmd = LanProtocolCmd.DEVICE_HINT
        self.payload_type = bytes([0])
        self._mode: Optional[bytes] = None
        self._device_address: Optional[bytes] = None

    def build_body(self) -> bool:
        if self._mode is not None and self._device_address is not None:
            self.request_data_body = self._mode + self._device_address
            return True
        return False

    def set_hint(self, mode: bytes, device_address: bytes) -> None:
        """Java 风格设定器:mode = DeviceMode.MODE_FLASH / MODE_PING。"""
        self._mode = mode
        self._device_address = device_address

    @property
    def mode(self) -> Optional[bytes]:
        return self._mode

    @property
    def device_address(self) -> Optional[bytes]:
        return self._device_address