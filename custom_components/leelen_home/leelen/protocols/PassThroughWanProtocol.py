import struct
import threading
from typing import Optional

from ..protocols.BaseWanProtocol import BaseWanProtocol
from ..utils.CRC8Utils import CRC8Utils
from ..ConnectLan import ConnectLan
from ..entity.GatewayInfo import GatewayInfo
from ..common import LeelenConst
from ..common import ProtocolDefault, WanProtocolCmd
from ..utils.LogUtils import LogUtils
from ..models.WanDataHandleModel import WanDataHandleModel


class PassThroughWanProtocol(BaseWanProtocol):
    LEN_LAN_NO_PASS = 28
    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        super().__init__()
        self.TAG = self.__class__.__name__
        self.dest = None
        self.source = None
        self.lan_protocol_ver = ProtocolDefault.PROTOCOL_VER_LAN
        self.m_lan_data = None
        self.cmd = WanProtocolCmd.PASS_THROUGH

    @classmethod
    def get_instance(cls):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = PassThroughWanProtocol()
        return cls._instance

    def build_lan_data(self, data: bytes, gateway_desc: bytes, dest: bytes, seq: bytes) -> bytes:
        data_len = len(data)
        total_len = data_len + 28

        buffer = bytearray()
        buffer.extend(LeelenConst.LAN_SYNC_HEADER)
        buffer.extend(struct.pack('<H', data_len + 20 + 1))
        buffer.extend(self.lan_protocol_ver)
        buffer.extend(gateway_desc)
        buffer.extend(dest)
        buffer.extend(seq)
        buffer.extend(data)

        crc = CRC8Utils.calc_shift_val(buffer, total_len)

        result = bytearray()
        result.extend(buffer)
        result.append(crc)
        return bytes(result)

    def get_pass_data(self, data: bytes) -> Optional[bytes]:
        if not data:
            return None
        if len(data) < 42:
            LogUtils.e(self.TAG, f"getPassData() data length = {len(data)}, < 42")
            return None

        data_len = len(data)
        header = data[:28]
        body = data[28:-1]
        crc = data[-1:]
        return body

    def is_login_lan(self, data: bytes) -> bool:
        if not data:
            return False
        if len(data) < 14:
            return True

        data_len = len(data)
        buffer = memoryview(data)

        sync_header = buffer[0:2]
        length = buffer[2:4]
        ver = buffer[4:6]
        seq = buffer[6:8]
        cmd = buffer[8:12]
        action = buffer[12:13]
        remain = buffer[13:]

        if seq[1] < 0 and action[0] == 0 and remain[0] == 6:
            return False

        return True

    def build_body(self) -> bool:
        data = self.m_lan_data
        if not data:
            LogUtils.e(self.TAG, "mLanData is null.")
            return False

        pass_data = self.get_pass_data(data)
        if pass_data and len(pass_data) > 0:
            self.request_data_body = pass_data
            return True

        LogUtils.e(self.TAG, "passData is empty.")
        return False

    def build_head(self, source: bytes, dest: bytes) -> bool:
        with self._lock:
            wan_server_code = GatewayInfo.get_instance().get_wan_server_code()
            if not wan_server_code:
                LogUtils.d(self.TAG, "buildHead() wan server id is null")
                WanDataHandleModel.get_instance().request_wan_server_id()
                return False

            buffer = bytearray()
            self.source = source
            self.dest = dest
            self.length = self.head_length + self.tail_length + len(self.request_data_body)

            buffer.extend(LeelenConst.WAN_SYNC_HEADER)
            buffer.extend(self.protocol_ver)
            buffer.extend(self.cmd)
            buffer.extend(wan_server_code)
            buffer.extend(struct.pack('<H', BaseWanProtocol.get_seq()))
            buffer.extend(self.action_type)
            buffer.extend(self.encrypted)
            buffer.extend(struct.pack('<I', self.length))
            buffer.extend(self.source)
            buffer.extend(self.dest)

            self.request_data_head = bytes(buffer)
            return True

    def get_request_data(self) -> bytes:
        return self.get_request_data(self.source, self.dest)

    def handle_pass_through_callback(self, data: bytes) -> None:
        if not data:
            LogUtils.e(self.TAG, "no data to handle.")
            return

        # LogUtils.e(ConvertUtils.bytes_to_hex(data), " ---- handlePassThroughData")

        try:
            buffer = memoryview(data)
            header = buffer[0:3]
            ver = buffer[3:5]
            cmd = buffer[5:7]
            seq = buffer[7:9]
            length = buffer[9:11]
            encrypt = buffer[11:12]
            action = buffer[12:13]
            server_id = buffer[13:17]
            src = buffer[17:25]
            dest = buffer[25:33]

            if encrypt[0] != 0:
                crc = buffer[33:34]
                pos = 34
            else:
                pos = 33

            remain_len = len(data) - 36
            if remain_len <= 0:
                return

            pass_data = data[pos:pos + remain_len]

            if not self.is_login_lan(pass_data):
                LogUtils.d(self.TAG, "handlePassThroughCallback() no login gateway")
            else:
                LogUtils.d(self.TAG, "handlePassThroughCallback() pass through data to lan")
                if src == GatewayInfo.get_instance().get_gateway_desc():
                    lan_data = self.build_lan_data(pass_data, src, dest, seq)
                    ConnectLan.get_instance().handle_pass_through_data(lan_data)

        except Exception as e:
            LogUtils.e(self.TAG, f"Error handling callback: {str(e)}")

    def set_lan_data(self, data: bytes) -> None:
        self.m_lan_data = data

    def set_src_dest(self, source: bytes, dest: bytes) -> None:
        self.source = source
        self.dest = dest
