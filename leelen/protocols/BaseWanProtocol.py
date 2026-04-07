import threading
from typing import Optional

from ..common import LeelenConst
from ..common import ProtocolDefault
from ..utils.ConvertUtils import ConvertUtils
from ..utils.LogUtils import LogUtils


class BaseWanProtocol:
    LENGTH_MIN = 36
    TAG = "BaseWanProtocol"
    _i_seq = 9
    _i_session_id = 0
    _seq_lock = threading.Lock()
    _session_lock = threading.Lock()

    def __init__(self):
        self.action_type = 0
        self.body_length = 0
        self.checksum = 0
        self.cmd = None
        self.dest = None
        self.encrypted = 0
        self.head_length = 33
        self.length = 0
        self.protocol_ver = ProtocolDefault.PROTOCOL_VER_WAN
        self.request_data = None
        self.request_data_body = None
        self.request_data_head = None
        self.request_data_tail = None
        self.reserved_bytes = bytes([0xFF, 0xFF])
        self.response_code = 0
        self.session_id = None
        self.source = None
        self.tail_length = 3

    @classmethod
    def get_seq(cls) -> int:
        with cls._seq_lock:
            seq = cls._i_seq
            cls._i_seq = (cls._i_seq + 1) & 0xFFFF
            return seq

    @classmethod
    def get_session_id(cls) -> int:
        with cls._session_lock:
            session_id = cls._i_session_id
            cls._i_session_id += 1
            return session_id

    @classmethod
    def parse(cls, data: bytes) -> Optional['BaseWanProtocol']:
        if not data:
            LogUtils.e(cls.TAG, "data is None")
            return None

        if len(data) == 0:
            LogUtils.e(cls.TAG, "data length = 0")
            return None

        if len(data) < cls.LENGTH_MIN:
            LogUtils.e(cls.TAG, f"data length = {len(data)}, < {cls.LENGTH_MIN}, invalid.")
            return None

        try:
            protocol = cls()

            # Parse header
            protocol.request_data_head = data[:protocol.head_length]
            header = memoryview(protocol.request_data_head)

            sync_header = header[0:3]
            protocol.protocol_ver = bytes(header[3:5])
            protocol.cmd = bytes(header[5:7])
            protocol.session_id = bytes(header[7:11])
            protocol.action_type = header[11]
            protocol.encrypted = header[12]
            protocol.length = ConvertUtils.to_int(header[13:17])
            protocol.source = bytes(header[17:25])
            protocol.dest = bytes(header[25:33])

            if len(data) != protocol.length:
                LogUtils.e(cls.TAG, f"data length {len(data)}, parse length {protocol.length}, not equal.")
                return None

            protocol.body_length = protocol.length - protocol.head_length - protocol.tail_length

            # Parse response code if action type is 1
            offset = protocol.head_length
            if protocol.action_type == 1:
                protocol.response_code = data[offset]
                offset += 1
                protocol.body_length -= 1

            # Parse body
            protocol.request_data_body = data[offset:offset + protocol.body_length]
            offset += protocol.body_length

            # Parse tail
            protocol.request_data_tail = data[offset:]
            protocol.reserved_bytes = protocol.request_data_tail[0:2]
            protocol.checksum = protocol.request_data_tail[2]

            protocol.request_data = data
            return protocol

        except Exception as e:
            LogUtils.e(cls.TAG, f"Parse error: {str(e)}")
            return None

    def build_body(self) -> bool:
        with threading.Lock():
            self.request_data_body = bytes()
            return True

    def build_head(self, source: bytes, dest: bytes) -> bool:
        with threading.Lock():
            try:
                self.source = source
                self.dest = dest
                self.length = self.head_length + self.tail_length + len(self.request_data_body)

                buffer = bytearray()
                buffer.extend(LeelenConst.WAN_SYNC_HEADER)
                buffer.extend(self.protocol_ver)
                buffer.extend(self.cmd)
                buffer.extend(ConvertUtils.to_bytes(self.get_session_id()))
                buffer.append(self.action_type)
                buffer.append(self.encrypted)
                buffer.extend(ConvertUtils.to_bytes(self.length, little_endian=True))
                buffer.extend(self.source)
                buffer.extend(self.dest)

                self.request_data_head = bytes(buffer)
                return True

            except Exception as e:
                LogUtils.e(self.TAG, f"Build head error: {str(e)}")
                return False

    def build_tail(self):
        self.checksum = self._get_check_byte(self.request_data_head,
                                             self.request_data_body,
                                             self.reserved_bytes)
        buffer = bytearray()
        buffer.extend(self.reserved_bytes)
        buffer.append(self.checksum)
        self.request_data_tail = bytes(buffer)

    def get_request_data(self, source: bytes, dest: bytes) -> Optional[bytes]:
        LogUtils.i(self.TAG, "getRequestData")

        if not self.build_body():
            LogUtils.e(self.TAG, "buildBody failed.")
            return None

        if not self.build_head(source, dest):
            LogUtils.e(self.TAG, "buildHead failed.")
            return None

        self.build_tail()

        buffer = bytearray()
        buffer.extend(self.request_data_head)
        buffer.extend(self.request_data_body)
        buffer.extend(self.request_data_tail)
        return bytes(buffer)

    def _get_check_byte(self, *byte_arrays: bytes) -> int:
        total = 0
        for byte_array in byte_arrays:
            total += sum(byte_array)
        return (-total) & 0xFF

    def get_cmd(self) -> bytes:
        return self.cmd

    def get_request_data_body(self) -> bytes:
        return self.request_data_body

    def get_ascii_password(self, password: str) -> bytes:
        """
        Converts a password string to a fixed-length (32 bytes) ASCII representation.
        Similar to the Java version but with Pythonic error handling.

        Args:
            password: Input password string

        Returns:
            32-byte array with the password encoded in reverse order with ISO-8859-1 encoding,
            padded if necessary
        """
        buffer = bytearray(32)  # Equivalent to ByteBuffer.allocate(32)

        if not password:
            return bytes(buffer)

        try:
            encoded = password.encode('iso-8859-1')
            pass_len = len(encoded)

            for i in range(32):
                if i < pass_len:
                    # Reverse positioning logic from Java version
                    pos = (pass_len - 1 + (32 - pass_len) - i)
                    buffer[i] = encoded[pos] if 0 <= pos < pass_len else 0xFF
                else:
                    buffer[i] = 0xFF  # Default padding

        except Exception as e:
            LogUtils.e(f"Error encoding password: {e}")
            # Return buffer with default values as in Java version
            return bytes(buffer)

        return bytes(buffer)

    def get_ascii_username(self, username: str) -> bytes:
        """
        Converts a username string to a fixed-length (20 bytes) ASCII representation.

        Args:
            username: Input username string

        Returns:
            20-byte array with the username encoded in reverse order with ISO-8859-1 encoding,
            padded with 0xFF at the beginning if needed
        """
        buffer = bytearray(20)  # Equivalent to ByteBuffer.allocate(20)

        if not username:
            return bytes(buffer)

        try:
            encoded = username.encode('iso-8859-1')
            pad_len = 20 - len(encoded)

            for i in range(20):
                if i < pad_len:
                    buffer[i] = 0xFF  # Padding
                else:
                    # Reverse positioning logic from Java version
                    pos = (len(encoded) - 1 + pad_len - i)
                    buffer[i] = encoded[pos] if 0 <= pos < len(encoded) else 0xFF

        except Exception as e:
            LogUtils.e(f"Error encoding username: {e}")
            # Return buffer with default values as in Java version
            return bytes(buffer)

        return bytes(buffer)

    def get_check_byte(self, *args: bytes) -> int:
        """
        Calculates a check byte by summing all bytes in the input arrays
        and returning the two's complement of the sum (equivalent to 0 - sum).

        Args:
            *args: Variable number of byte arrays (bytes or bytearray objects)

        Returns:
            The check byte as an integer (0-255)
        """
        total = 0

        for byte_array in args:
            for byte in byte_array:
                total += byte

        # Calculate two's complement equivalent to Java's (0 - total)
        # Using bitwise AND with 0xFF to get unsigned byte value
        return (0 - total) & 0xFF
