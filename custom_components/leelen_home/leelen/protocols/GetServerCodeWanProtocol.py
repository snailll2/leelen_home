from typing import Optional
import uuid
import struct

from ..protocols.BaseWanProtocol import BaseWanProtocol
from ..utils.ConvertUtils import ConvertUtils
from ..entity.GatewayInfo import GatewayInfo
from ..common import LeelenConst
from ..common import WanProtocolCmd, DeviceType
from ..entity.User import User


class GetServerCodeWanProtocol(BaseWanProtocol):
    _instance: Optional['GetServerCodeWanProtocol'] = None

    def __init__(self):
        super().__init__()
        self.cmd = WanProtocolCmd.GET_GATEWAY_SERVER

    @classmethod
    def get_instance(cls) -> 'GetServerCodeWanProtocol':
        if not cls._instance:
            cls._instance = GetServerCodeWanProtocol()
        return cls._instance

    def build_body(self) -> bool:
        with self._seq_lock:
            by_array = ConvertUtils.get_address_by_type(DeviceType.APP,
                                                        User.get_instance().get_account_id())
            uid = GatewayInfo.get_instance().get_uid()
            uuid_str = ""
            if not uid:
                uuid_str = str(uuid.uuid4()).replace("-", "")
                # SharePreferenceModel.set_uuid(uuid_str)

            uuid_bytes = uuid_str.encode()
            buffer = bytearray(49)
            buffer[0] = 16
            buffer[1:9] = by_array
            buffer[9:17] = b'\xff' * 8
            buffer[17:] = uuid_bytes
            self.request_data_body = bytes(buffer)
            return True

    def build_head(self, source: bytes, dest: bytes) -> bool:
        with self._seq_lock:
            buffer = bytearray(self.head_length)
            self.source = source
            self.dest = dest
            self.length = self.head_length + self.tail_length + len(self.request_data_body)

            pos = 0
            buffer[pos:pos + len(LeelenConst.WAN_SYNC_HEADER)] = LeelenConst.WAN_SYNC_HEADER
            pos += len(LeelenConst.WAN_SYNC_HEADER)
            buffer[pos] = self.protocol_ver
            pos += 1
            buffer[pos] = self.cmd
            pos += 1
            buffer[pos:pos + 2] = ConvertUtils.to_bytes(BaseWanProtocol.get_session_id())
            pos += 2
            buffer[pos:pos + 2] = ConvertUtils.to_bytes(BaseWanProtocol.get_seq())
            pos += 2
            buffer[pos] = self.action_type
            pos += 1
            buffer[pos] = self.encrypted
            pos += 1
            buffer[pos:pos + 4] = struct.pack('<I', self.length)
            pos += 4
            buffer[pos:pos + len(self.source)] = self.source
            pos += len(self.source)
            buffer[pos:pos + len(self.dest)] = self.dest

            self.request_data_head = bytes(buffer)
            return True
