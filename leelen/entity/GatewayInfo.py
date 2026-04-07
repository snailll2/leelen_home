import array
# import logging
import uuid
from threading import Lock

from ..common import DeviceType, ProtocolDefault
from ..common import LeelenConst
from ..utils.ConvertUtils import ConvertUtils
from ..utils.LogUtils import LogUtils


class GatewayInfo:
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
        self.gateway_name = ""
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
        self.gateway_name = "Zigbee无线网"

    @classmethod
    def get_instance(cls):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = cls()
        return cls._instance

    def set_desc(self):
        pass

    def get_aes_key(self):
        return self.aes_key

    def get_gateway_desc(self):
        return self.gateway_desc

    def get_gateway_desc_string(self):
        return self.gateway_desc_string

    def get_gateway_name(self):
        return self.gateway_name

    def get_had_bind(self):
        return self.had_bind

    def get_lan_address_ip(self):
        LogUtils.d(f"{self.TAG}: getLanAddressIp() ip: {self.lan_address_ip}")
        return self.lan_address_ip

    def get_sub_tcp_server_code(self):
        return self.sub_tcp_server_code

    def get_tcp_server_code(self):
        return self.tcp_server_code

    def get_temp_gateway_desc(self):
        LogUtils.d(
            f"{self.TAG}: getTempGatewayDesc() tempGatewayDesc value {ConvertUtils.bytes_to_hex(self.temp_gateway_desc)}")
        return self.temp_gateway_desc

    def get_uid(self):
        return self.uid

    def get_wan_server_code(self):
        return self.wan_server_code

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
        # self.gateway_desc = desc
        # self.gateway_desc_string = ConvertUtils.bytes_to_hex(ConvertUtils.reverse(desc))

    def set_gateway_name(self, name):
        self.gateway_name = name

    def set_had_bind(self, had_bind):
        self.had_bind = had_bind

    def set_lan_address_ip(self, ip):
        self.lan_address_ip = ip

    def set_sub_tcp_server_code(self, code):
        self.sub_tcp_server_code = code

    def set_tcp_server_code(self, code):
        self.tcp_server_code = code

    def set_temp_gateway_desc(self, desc):
        LogUtils.d(f"{self.TAG}: setTempGatewayDesc() tempGatewayDesc value {ConvertUtils.bytes_to_hex(desc)}")
        self.temp_gateway_desc = desc

    def set_wan_server_code(self, code):
        self.wan_server_code = code
