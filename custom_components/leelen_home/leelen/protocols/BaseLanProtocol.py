import threading
from typing import Optional

from ..common import LeelenConst
from ..common import ProtocolDefault
from ..entity.GatewayInfo import GatewayInfo
from ..utils.AesCoder import AesCoder
from ..utils.CRC8Utils import CRC8Utils
from ..utils.ConvertUtils import ConvertUtils
from ..utils.LogUtils import LogUtils


class BaseLanProtocol:
    _frame_id = 1
    _lock = threading.Lock()

    def __init__(self):
        self.TAG = self.__class__.__name__
        self.checksum = 0
        self.cmd = None
        self.dest = None
        self.device_dest = None
        self.device_source = None
        self.encrypted = None
        self.frame_id = None
        self.head_and_len = 8
        self.head_length = 41
        self.is_add_sub = False
        self.lan_protocol_ver = ProtocolDefault.PROTOCOL_VER_LAN
        self.length = 0
        self.payload_type = None
        self.request_data = None
        self.request_data_body = None
        self.request_data_head = None
        self.server_id = ProtocolDefault.DEFAULT_LAN_SERVER_ID
        self.source = None
        self.tail_length = 1

        self.encrypted = ProtocolDefault.LAN_NO_ENCRYPT
        self.device_source = bytes([0xFF, 0xFF])
        self.device_dest = bytes([0, 0])
        self.payload_type = bytes([1])

    @staticmethod
    def get_aes_real_body(data: bytes) -> bytes:
        decrypted = AesCoder.get_instance().decrypt("h9sv5JUzjeJKW81z", "9sng3f1cYsgQvEz5", data)
        buffer = memoryview(decrypted)
        length = ConvertUtils.to_unsigned_short(buffer[0:2])
        return bytes(buffer[2:2 + length])

    @classmethod
    def get_frame_id(cls) -> int:
        # with cls._lock:
        if cls._frame_id >= 65535:
            cls._frame_id = 1
        frame_id = cls._frame_id
        cls._frame_id += 1
        return frame_id

    @staticmethod
    def parse(data: bytes) -> Optional['BaseLanProtocol']:
        if not data:
            LogUtils.e("BaseLanProtocol", "data == null")
            return None
        if len(data) == 0:
            LogUtils.e("BaseLanProtocol", "data length = 0")
            return None
        if len(data) < 42:
            LogUtils.e("BaseLanProtocol", f"data length = {len(data)}, < 42, invalid.")
            return None

        try:
            protocol = BaseLanProtocol()
            buffer = memoryview(data)

            protocol.request_data_head = bytes(buffer[0:protocol.head_length])
            head_buffer = memoryview(protocol.request_data_head)

            sync_header = head_buffer[0:4]
            length_bytes = head_buffer[4:8]
            protocol.lan_protocol_ver = bytes(head_buffer[8:10])
            protocol.source = bytes(head_buffer[10:18])
            protocol.dest = bytes(head_buffer[18:26])
            protocol.server_id = bytes(head_buffer[26:28])
            protocol.encrypted = bytes(head_buffer[28:30])
            protocol.device_source = bytes(head_buffer[30:32])
            protocol.device_dest = bytes(head_buffer[32:34])
            protocol.cmd = bytes(head_buffer[34:36])
            protocol.frame_id = bytes(head_buffer[36:40])
            protocol.payload_type = bytes(head_buffer[40:41])

            protocol.length = ConvertUtils.to_int(length_bytes)

            body_len = protocol.length + protocol.head_and_len - protocol.head_length - protocol.tail_length
            protocol.request_data_body = bytes(buffer[protocol.head_length:protocol.head_length + body_len])

            if protocol.encrypted != bytes([0, 0]):
                protocol.request_data_body = BaseLanProtocol.get_aes_real_body(protocol.request_data_body)

            protocol.checksum = buffer[protocol.head_length + body_len]
            protocol.request_data = data
            return protocol

        except Exception as e:
            LogUtils.e("BaseLanProtocol", f"Error parsing: {str(e)}")
            return None

    def build_body(self) -> bool:
        with self._lock:
            self.request_data_body = bytes()
            return True

    def build_head(self, source: bytes, dest: bytes, device_dest: bytes) -> bool:
        with self._lock:
            try:
                buffer = bytearray()
                self.source = source
                self.dest = dest
                self.device_dest = device_dest

                self.length = self.head_length - self.head_and_len + self.tail_length
                if self.request_data_body:
                    self.length += len(self.request_data_body)

                buffer.extend(LeelenConst.LAN_SYNC_HEADER)
                buffer.extend(ConvertUtils.to_bytes(self.length, 'little'))
                buffer.extend(bytes([0, 0]))
                buffer.extend(self.lan_protocol_ver)
                buffer.extend(self.source)
                buffer.extend(self.dest)

                if self.is_add_sub:
                    buffer.extend(GatewayInfo.get_instance().get_sub_tcp_server_code())
                else:
                    buffer.extend(GatewayInfo.get_instance().get_tcp_server_code())

                buffer.extend(self.encrypted)

                if self.is_add_sub:
                    buffer.extend(GatewayInfo.get_instance().get_sub_tcp_server_code())
                else:
                    buffer.extend(GatewayInfo.get_instance().get_tcp_server_code())

                buffer.extend(self.device_dest)
                buffer.extend(self.cmd)

                self.frame_id = ConvertUtils.to_bytes(self.get_frame_id())
                buffer.extend(self.frame_id)
                buffer.extend(bytes([0, 0]))

                # buffer.extend(bytes([63, 0, 0, 0]))

                buffer.extend(self.payload_type)

                self.request_data_head = bytes(buffer)
                return True

            except Exception as e:
                LogUtils.e(self.TAG, f"Error building head: {str(e)}")
                return False

    def get_request_data(self, source: bytes = bytes(8), dest: bytes = bytes(8), device_dest: bytes = bytes(2)) -> \
            Optional[bytes]:
        if not self.build_body():
            LogUtils.e(self.TAG, "buildBody failed.")
            return None

        try:
            if self.request_data_body and self.encrypted != bytes([0, 0]):
                body_len = len(self.request_data_body)
                len_bytes = ConvertUtils.to_bytes(body_len)

                buffer = bytearray()
                buffer.extend(len_bytes)
                buffer.extend(self.request_data_body)
                self.request_data_body = AesCoder.get_instance().encrypt(
                    "h9sv5JUzjeJKW81z",
                    "9sng3f1cYsgQvEz5",
                    bytes(buffer)
                )
        except Exception as e:
            LogUtils.e(self.TAG, f"Error encrypting body: {str(e)}")

        if device_dest is None:
            device_dest = bytes([0, 0])

        if not self.build_head(source, dest, device_dest):
            LogUtils.e(self.TAG, "buildHead failed.")
            return None

        if self.request_data_body:
            buffer = bytearray()
            buffer.extend(self.request_data_head)
            buffer.extend(self.request_data_body)

            self.checksum = CRC8Utils.calc_shift_val(buffer, len(buffer))

            result = bytearray()
            result.extend(buffer)
            result.append(self.checksum)
            return bytes(result)
        else:
            buffer = bytearray()
            buffer.extend(self.request_data_head)

            self.checksum = CRC8Utils.calc_shift_val(buffer, len(buffer))

            result = bytearray()
            result.extend(buffer)
            result.append(self.checksum)
            return bytes(result)
