import uuid
import struct

from ..protocols.BaseWanProtocol import BaseWanProtocol
from ..entity.GatewayInfo import GatewayInfo
from ..common import LeelenConst
from ..common import WanProtocolCmd, DeviceType
from ..entity.User import User
from ..utils.ConvertUtils import ConvertUtils


class GetServerCodeWanProtocol(BaseWanProtocol):

    def __init__(self):
        super().__init__()
        self.cmd = WanProtocolCmd.GET_GATEWAY_SERVER

    def build_body(self) -> bool:
        # 注意:外层必须用实例锁 self._lock,不能用 self._seq_lock(类锁)。
        # build_head 内部会调 BaseWanProtocol.get_seq()/get_session_id(),
        # 它们以 _seq_lock/_session_lock (threading.Lock,不可重入)做 classmethod 加锁。
        # 若这里再套 _seq_lock,get_seq() 会重复获取同一把锁 → 自死锁(faulthandler 实测挂死)。
        # Java 原版 buildHead/buildBody 是 synchronized(this) → 对应实例锁。
        with self._lock:
            by_array = ConvertUtils.get_long_address_by_type(
                DeviceType.APP, User.get_instance().account_id)
            uid = GatewayInfo.get_instance().uid
            uuid_str = ""
            if not uid:
                uuid_str = str(uuid.uuid4()).replace("-", "")
                # SharePreferenceModel.set_uuid(uuid_str)

            uuid_bytes = uuid_str.encode()
            buffer = bytearray(49)
            buffer[0] = 16
            buffer[1:9] = by_array
            buffer[9:17] = b'\xff' * 8
            # 注意:空 uuid_bytes 时不能用 buffer[17:] = b'' —— Python 的
            # slice 赋值会截断 bytearray(变成 17B)。Java 原版是预置 49B 数组,
            # 无份额外信息时保持全 0。这里只在非空时才写。
            if uuid_bytes:
                buffer[17:17 + len(uuid_bytes)] = uuid_bytes
            self.request_data_body = bytes(buffer)
            return True

    def build_head(self, source: bytes, dest: bytes) -> bool:
        with self._lock:
            buffer = bytearray(self.head_length)
            self.source = source
            self.dest = dest
            self.length = self.head_length + self.tail_length + len(self.request_data_body)

            pos = 0
            buffer[pos:pos + len(LeelenConst.WAN_SYNC_HEADER)] = LeelenConst.WAN_SYNC_HEADER
            pos += len(LeelenConst.WAN_SYNC_HEADER)
            buffer[pos:pos + 2] = self.protocol_ver
            pos += 2
            buffer[pos:pos + 2] = self.cmd
            pos += 2
            # 与 Java 原版一致:GetServerCode 的 head 是 session(short)+seq(short),
            # 不同于 Base 的 session(int)。必须固定 2 字节小端,不能靠 ConvertUtils.to_bytes
            # (对 short 区间恰好 2 字节,但 session/seq 递增超过 32767 后会变 4 字节错位)。
            buffer[pos:pos + 2] = (BaseWanProtocol.get_session_id() & 0xFFFF).to_bytes(2, "little")
            pos += 2
            buffer[pos:pos + 2] = (BaseWanProtocol.get_seq() & 0xFFFF).to_bytes(2, "little")
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