from typing import Optional

from ..protocols.BaseLanProtocol import BaseLanProtocol
from ..common import LanProtocolCmd


class AppDevicePassThroughLanProtocol(BaseLanProtocol):
    """App 设备属性透传指令(cmd PASS_THROUGH_APP_DEVICE = [1, 6])。

    官方 App 写窗帘电机方向/重置行程(updateCurtainMotorDirectionAndResetStroke)
    时下发并期待 handleDevicePassThrough 响应的指令:cmd = [1, 6],载荷不再是
    DEV_CTRL 的 TLV,而是 ``appDevicePassThrough`` 拼好的原始字节:
    ``[01 TA][len][0x64 写私有属性][property_id][val_len][val]``。

    目标地址仍按 LED 协议帧头的 deviceDest 段传**逻辑通道地址**(窗帘电机的
    可写属性挂在 logic_addr,不是 dev_addr —— dump.db 实测属性 163 在 225/241)。
    """

    def __init__(self):
        super().__init__()
        self.cmd = LanProtocolCmd.PASS_THROUGH_APP_DEVICE
        self.payload_type = bytes([0])
        self._payload: Optional[bytes] = None

    def build_body(self) -> bool:
        if self._payload is not None:
            self.request_data_body = self._payload
            return True
        return False

    def set_payload_data(self, data: bytes) -> None:
        """Java 风格设定器:把 appDevicePassThrough 拼好的负载整段粘进 body。"""
        self._payload = data

    @property
    def payload(self) -> Optional[bytes]:
        return self._payload