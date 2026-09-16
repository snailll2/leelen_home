import array
import uuid
from threading import Lock

from ..common import DeviceType, ProtocolDefault
from ..common import LeelenConst
from ..utils.ConvertUtils import ConvertUtils
from ..utils.LogUtils import LogUtils


class GatewayInfo:
    """网关运行时状态 —— 纯数据持有,字段即状态,直接属性读写。

    遗留:Java getter/setter 包装(get_*/set_*)已清除。
    保留真方法:set_gateway_desc(派生两个字段)、had_wan_server_code/is_default_gateway(派生判定)、reset/set_desc。
    """

    TAG = "GatewayInfo"
    _instance = None
    _lock = Lock()

    def __init__(self):
        self.aes_key = "9sng3f1cYsgQvEz5"
        self.default_desc = ConvertUtils.get_desc_address_by_type(
            DeviceType.HOST,
            LeelenConst.ALL_FF_DESC
        )
        self.gateway_desc = self.default_desc
        self.gateway_name = "Zigbee无线网"
        self.had_bind = False
        self.lan_address_ip = ""
        self.gateway_desc_string = ConvertUtils.bytes_to_hex(
            ConvertUtils.reverse(self.default_desc)
        )
        self.sub_tcp_server_code = ProtocolDefault.DEFAULT_LAN_SERVER_ID
        self.tcp_server_code = ProtocolDefault.DEFAULT_LAN_SERVER_ID
        self.temp_gateway_desc = self.default_desc
        self.uid = str(uuid.uuid4()).replace("-", "")
        self.wan_server_code = ProtocolDefault.DEFAULT_WAN_SERVER_ID

    @classmethod
    def get_instance(cls):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = cls()
        return cls._instance

    def set_desc(self):
        pass

    def had_wan_server_code(self):
        return (self.wan_server_code is not None and
                not array.array('B', self.wan_server_code) == array.array('B', ProtocolDefault.DEFAULT_LAN_SERVER_ID))

    def is_default_gateway(self):
        return array.array('B', self.gateway_desc) == array.array('B', self.default_desc)

    def reset(self):
        LogUtils.d(f"{self.TAG}: reset()")
        self.tcp_server_code = ProtocolDefault.DEFAULT_LAN_SERVER_ID
        self.wan_server_code = ProtocolDefault.DEFAULT_WAN_SERVER_ID
        self.lan_address_ip = ""
        self.gateway_name = ""
        self.aes_key = "9sng3f1cYsgQvEz5"
        self.gateway_desc = self.default_desc
        self.temp_gateway_desc = self.default_desc
        self.gateway_desc_string = ConvertUtils.bytes_to_hex(
            ConvertUtils.reverse(self.default_desc)
        )
        self.had_bind = False
        self.uid = str(uuid.uuid4()).replace("-", "")

    def set_gateway_desc(self, desc):
        self.gateway_desc_string = desc
        self.gateway_desc = ConvertUtils.hex_to_bytes(desc, "little")

        LogUtils.d(
            f"{self.TAG}: setGatewayDesc() gatewayDesc value {self.gateway_desc_string},{self.gateway_desc}")