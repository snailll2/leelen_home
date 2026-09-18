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
    _lock = threading.Lock()

    def __init__(self):
        super().__init__()
        self.TAG = self.__class__.__name__
        self.dest = None
        self.source = None
        self.lan_protocol_ver = ProtocolDefault.PROTOCOL_VER_LAN
        self.m_lan_data = None
        self.cmd = WanProtocolCmd.PASS_THROUGH

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

        # Java 原版 ByteBuffer.allocate(data_len + 28) 会将剩余字节补 0,
        # 再对完整 total_len 计算 CRC。Python bytearray() 只 append 了实际
        # 字段(共 data_len+26),直接按 total_len 遍历会越界 (IndexError)。
        # 补齐到 total_len 再算,与 Java 完全一致。
        if len(buffer) < total_len:
            buffer.extend(b'\x00' * (total_len - len(buffer)))
        crc = CRC8Utils.calc_shift_val(buffer, total_len)

        result = bytearray()
        result.extend(buffer)
        result.append(crc)
        return bytes(result)

    def get_pass_data(self, data: bytes) -> Optional[bytes]:
        """取出 PassThrough 帧的 body。

        帧布局(共 42 字节起,末尾 1 字节 CRC):
            0..27   头部(28B)
            28..-2  body
            -1      CRC8
        """
        if not data:
            return None
        if len(data) < 42:
            LogUtils.e(self.TAG, f"getPassData() data length = {len(data)}, < 42")
            return None

        return data[28:-1]

    def is_login_lan(self, data: bytes) -> bool:
        """判断该 WAN 帧是否属于 LAN 登录(非 LAN 登录帧返回 False)。

        帧布局(偏移,长度):
            0..1  sync_header   2..3  length   4..5  ver
            6..7  seq           8..11 cmd      12     action
            13..  remain(其余全部)
        当前只有 seq/action/remain 参与判定,其余字段保留在布局表里供对照。
        """
        if not data:
            return False
        if len(data) < 14:
            return True

        buffer = memoryview(data)
        seq = buffer[6:8]
        action = buffer[12:13]
        remain = buffer[13:]

        # 注意:Python bytes 无符号,seq[1] < 0 恒为 False,此分支实际永不执行(Java 直译残留)。
        # 原语义是「某种 WAN 帧不算 LAN 登录」,但真机字节格式未确认 —— 待真机验证,
        # 未强行反转以避免改变设备行为。
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
            wan_server_code = GatewayInfo.get_instance().wan_server_code
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
            buffer.append(self.action_type)
            buffer.append(self.encrypted)
            buffer.extend(struct.pack('<I', self.length))
            buffer.extend(self.source)
            buffer.extend(self.dest)

            self.request_data_head = bytes(buffer)
            return True

    def get_request_data(self) -> bytes:
        # Java 原版:无参 getRequestData() 是重载,委托给基类的
        # getRequestData(source, dest)。Python 无重载,self.get_request_data(...)
        # 会无限自调用(递归到自身)→ TypeError,控制帧永远发不出去。
        # 必须显式调基类方法。
        return BaseWanProtocol.get_request_data(self, self.source, self.dest)

    def handle_pass_through_callback(self, data: bytes) -> None:
        if not data:
            LogUtils.e(self.TAG, "no data to handle.")
            return

        # LogUtils.e(ConvertUtils.bytes_to_hex(data), " ---- handlePassThroughData")

        try:
            buffer = memoryview(data)
            # 帧布局(偏移,长度):
            #   0..2 header  3..4 ver   5..6 cmd   7..8 seq   9..10 length
            #   11   encrypt 12   action 13..16 server_id 17..24 src 25..32 dest
            #   33   crc(仅 encrypt != 0 时存在)
            # 当前只用 encrypt(决定是否有 CRC 字节)/ seq / src / dest,其余字段保留在此
            # 布局表里备查,不再逐个取出为局部变量。
            encrypt = buffer[11:12]
            seq = buffer[7:9]
            src = buffer[17:25]
            dest = buffer[25:33]

            pos = 34 if encrypt[0] != 0 else 33

            remain_len = len(data) - 36
            if remain_len <= 0:
                return

            pass_data = data[pos:pos + remain_len]

            if not self.is_login_lan(pass_data):
                LogUtils.d(self.TAG, "handlePassThroughCallback() no login gateway")
            else:
                LogUtils.d(self.TAG, "handlePassThroughCallback() pass through data to lan")
                if src == GatewayInfo.get_instance().gateway_desc:
                    lan_data = self.build_lan_data(pass_data, src, dest, seq)
                    # Java 原版调 ConnectLan.handlePassThroughData → pushLan/pullLan →
                    # handleProtocolData。Python 同义方法是 handle_recv_data(同样的
                    # push_lan → pull_lan → handle_protocol_data),handle_pass_through_data 不存在。
                    ConnectLan.get_instance().handle_recv_data(lan_data)

        except Exception as e:
            LogUtils.e(self.TAG, f"Error handling callback: {str(e)}")

    def set_lan_data(self, data: bytes) -> None:
        self.m_lan_data = data

    def set_src_dest(self, source: bytes, dest: bytes) -> None:
        self.source = source
        self.dest = dest
