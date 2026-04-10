"""
广域网协议基类

提供广域网通信协议的基础功能，包括：
- 协议数据解析
- 协议数据构建
- 用户名/密码编码
- 校验和计算

Classes:
    BaseWanProtocol: 广域网协议基类
"""

import threading
from typing import Optional, ClassVar
from dataclasses import dataclass, field

from ..common import LeelenConst, ProtocolDefault
from ..utils.ConvertUtils import ConvertUtils
from ..utils.LogUtils import LogUtils
from ..utils.Exceptions import ProtocolException, safe_execute


@dataclass
class WanProtocolHeader:
    """
    广域网协议头结构

    Attributes:
        sync_header: 同步头 (3 bytes)
        protocol_ver: 协议版本 (2 bytes)
        cmd: 命令 (2 bytes)
        session_id: 会话ID (4 bytes)
        action_type: 动作类型 (1 byte)
        encrypted: 加密标志 (1 byte)
        length: 数据长度 (4 bytes)
        source: 源地址 (8 bytes)
        dest: 目的地址 (8 bytes)
    """
    sync_header: bytes = field(default_factory=lambda: LeelenConst.WAN_SYNC_HEADER)
    protocol_ver: bytes = field(default_factory=lambda: ProtocolDefault.PROTOCOL_VER_WAN)
    cmd: bytes = field(default_factory=lambda: bytes(2))
    session_id: bytes = field(default_factory=lambda: bytes(4))
    action_type: int = 0
    encrypted: int = 0
    length: int = 0
    source: bytes = field(default_factory=lambda: bytes(8))
    dest: bytes = field(default_factory=lambda: bytes(8))

    # 常量
    HEAD_LENGTH: ClassVar[int] = 33
    TAIL_LENGTH: ClassVar[int] = 3
    LENGTH_MIN: ClassVar[int] = 36

    def to_bytes(self) -> bytes:
        """将头部转换为字节"""
        buffer = bytearray()
        buffer.extend(self.sync_header)
        buffer.extend(self.protocol_ver)
        buffer.extend(self.cmd)
        buffer.extend(self.session_id)
        buffer.append(self.action_type)
        buffer.append(self.encrypted)
        buffer.extend(ConvertUtils.to_bytes(self.length, little_endian=True))
        buffer.extend(self.source)
        buffer.extend(self.dest)
        return bytes(buffer)


@dataclass
class WanProtocolTail:
    """
    广域网协议尾结构

    Attributes:
        reserved_bytes: 保留字节 (2 bytes)
        checksum: 校验和 (1 byte)
    """
    reserved_bytes: bytes = field(default_factory=lambda: bytes([0xFF, 0xFF]))
    checksum: int = 0

    def to_bytes(self) -> bytes:
        """将尾部转换为字节"""
        buffer = bytearray()
        buffer.extend(self.reserved_bytes)
        buffer.append(self.checksum)
        return bytes(buffer)


class BaseWanProtocol:
    """
    广域网协议基类

    提供WAN协议的基础功能，子类需要实现 build_body 方法。

    Attributes:
        TAG: 日志标签
        cmd: 命令字节
        response_code: 响应码
        session_id: 会话ID
    """

    # 类级别的序列号和锁
    _seq: ClassVar[int] = 9
    _session_id: ClassVar[int] = 0
    _seq_lock: ClassVar[threading.Lock] = threading.Lock()
    _session_lock: ClassVar[threading.Lock] = threading.Lock()

    # 常量
    LENGTH_MIN: ClassVar[int] = 36
    TAG: ClassVar[str] = "BaseWanProtocol"

    # 用户名/密码编码常量
    USERNAME_LENGTH: ClassVar[int] = 20
    PASSWORD_LENGTH: ClassVar[int] = 32
    PADDING_BYTE: ClassVar[int] = 0xFF

    def __init__(self):
        """初始化协议对象"""
        # 头部
        self._header = WanProtocolHeader()

        # 尾部
        self._tail = WanProtocolTail()

        # 数据部分
        self._request_data: Optional[bytes] = None
        self._request_data_body: Optional[bytes] = None
        self._request_data_head: Optional[bytes] = None
        self._request_data_tail: Optional[bytes] = None

        # 响应相关
        self.response_code: int = 0
        self.body_length: int = 0

    # region 属性访问

    @property
    def cmd(self) -> Optional[bytes]:
        """获取命令字节"""
        return self._header.cmd

    @cmd.setter
    def cmd(self, value: bytes) -> None:
        """设置命令字节"""
        self._header.cmd = value

    @property
    def session_id(self) -> Optional[bytes]:
        """获取会话ID"""
        return self._header.session_id

    @session_id.setter
    def session_id(self, value: bytes) -> None:
        """设置会话ID"""
        self._header.session_id = value

    @property
    def action_type(self) -> int:
        """获取动作类型"""
        return self._header.action_type

    @action_type.setter
    def action_type(self, value: int) -> None:
        """设置动作类型"""
        self._header.action_type = value

    @property
    def source(self) -> bytes:
        """获取源地址"""
        return self._header.source

    @property
    def dest(self) -> bytes:
        """获取目的地址"""
        return self._header.dest

    @property
    def request_data_body(self) -> Optional[bytes]:
        """获取请求数据体"""
        return self._request_data_body

    @request_data_body.setter
    def request_data_body(self, value: Optional[bytes]) -> None:
        """设置请求数据体"""
        self._request_data_body = value

    @property
    def request_data(self) -> Optional[bytes]:
        """获取完整请求数据"""
        return self._request_data

    # endregion

    # region 静态方法

    @classmethod
    def get_seq(cls) -> int:
        """
        获取下一个序列号

        Returns:
            递增的序列号（0-65535循环）
        """
        with cls._seq_lock:
            seq = cls._seq
            cls._seq = (cls._seq + 1) & 0xFFFF
            return seq

    @classmethod
    def get_session_id(cls) -> int:
        """
        获取下一个会话ID

        Returns:
            递增的会话ID
        """
        with cls._session_lock:
            session_id = cls._session_id
            cls._session_id += 1
            return session_id

    @classmethod
    def parse(cls, data: bytes) -> Optional['BaseWanProtocol']:
        """
        解析协议数据

        Args:
            data: 原始协议数据

        Returns:
            解析后的协议对象，失败返回None
        """
        if not data:
            LogUtils.e(cls.TAG, "Data is None")
            return None

        if len(data) == 0:
            LogUtils.e(cls.TAG, "Data length is 0")
            return None

        if len(data) < cls.LENGTH_MIN:
            LogUtils.e(cls.TAG, f"Data length {len(data)} < minimum {cls.LENGTH_MIN}")
            return None

        try:
            protocol = cls()

            # 解析头部
            header = WanProtocolHeader()
            header.sync_header = data[0:3]
            header.protocol_ver = bytes(data[3:5])
            header.cmd = bytes(data[5:7])
            header.session_id = bytes(data[7:11])
            header.action_type = data[11]
            header.encrypted = data[12]
            header.length = ConvertUtils.to_int(data[13:17])
            header.source = bytes(data[17:25])
            header.dest = bytes(data[25:33])

            protocol._header = header

            # 验证长度
            if len(data) != header.length:
                LogUtils.e(
                    cls.TAG,
                    f"Data length {len(data)} != parsed length {header.length}"
                )
                return None

            # 计算数据体长度
            protocol.body_length = (
                header.length -
                header.HEAD_LENGTH -
                header.TAIL_LENGTH
            )

            # 解析响应码（如果是响应包）
            offset = header.HEAD_LENGTH
            if header.action_type == 1:
                protocol.response_code = data[offset]
                offset += 1
                protocol.body_length -= 1

            # 解析数据体
            protocol._request_data_body = data[offset:offset + protocol.body_length]
            offset += protocol.body_length

            # 解析尾部
            tail = WanProtocolTail()
            tail.reserved_bytes = bytes(data[offset:offset + 2])
            tail.checksum = data[offset + 2]
            protocol._tail = tail

            protocol._request_data = data
            return protocol

        except Exception as e:
            LogUtils.e(cls.TAG, f"Parse error: {e}")
            return None

    # endregion

    # region 构建方法

    def build_body(self) -> bool:
        """
        构建协议体

        子类必须重写此方法。

        Returns:
            构建是否成功
        """
        self._request_data_body = bytes()
        return True

    def _build_head(self, source: bytes, dest: bytes) -> bool:
        """
        构建协议头

        Args:
            source: 源地址
            dest: 目的地址

        Returns:
            构建是否成功
        """
        try:
            self._header.source = source
            self._header.dest = dest
            self._header.session_id = ConvertUtils.to_bytes(self.get_session_id())
            self._header.length = (
                WanProtocolHeader.HEAD_LENGTH +
                WanProtocolHeader.TAIL_LENGTH +
                len(self._request_data_body or b'')
            )
            self._request_data_head = self._header.to_bytes()
            return True

        except Exception as e:
            LogUtils.e(self.TAG, f"Build head error: {e}")
            return False

    def _build_tail(self) -> None:
        """构建协议尾（包含校验和）"""
        self._tail.checksum = self._calculate_checksum(
            self._request_data_head,
            self._request_data_body,
            self._tail.reserved_bytes
        )
        self._request_data_tail = self._tail.to_bytes()

    def _calculate_checksum(self, *byte_arrays: bytes) -> int:
        """
        计算校验和

        对所有字节数组求和，取反后与0xFF相与。

        Args:
            *byte_arrays: 变长字节数组参数

        Returns:
            校验和字节值
        """
        total = sum(
            byte for array in byte_arrays if array
            for byte in array
        )
        return (-total) & 0xFF

    def get_request_data(self, source: bytes, dest: bytes) -> Optional[bytes]:
        """
        获取完整的请求数据

        Args:
            source: 源地址 (8 bytes)
            dest: 目的地址 (8 bytes)

        Returns:
            完整的协议数据，失败返回None
        """
        LogUtils.i(self.TAG, "Building request data")

        # 构建数据体
        if not self.build_body():
            LogUtils.e(self.TAG, "Build body failed")
            return None

        # 构建头部
        if not self._build_head(source, dest):
            LogUtils.e(self.TAG, "Build head failed")
            return None

        # 构建尾部
        self._build_tail()

        # 组装数据
        buffer = bytearray()
        buffer.extend(self._request_data_head)
        if self._request_data_body:
            buffer.extend(self._request_data_body)
        buffer.extend(self._request_data_tail)

        return bytes(buffer)

    # endregion

    # region 编码方法

    def encode_password(self, password: str) -> bytes:
        """
        编码密码

        将密码字符串转换为固定长度(32字节)的ASCII表示。
        使用反向编码和ISO-8859-1编码。

        Args:
            password: 密码字符串

        Returns:
            32字节的编码后密码
        """
        buffer = bytearray(self.PASSWORD_LENGTH)

        if not password:
            return bytes(buffer)

        try:
            encoded = password.encode('iso-8859-1')
            pass_len = len(encoded)

            for i in range(self.PASSWORD_LENGTH):
                if i < pass_len:
                    # 反向定位逻辑
                    pos = (pass_len - 1 + (self.PASSWORD_LENGTH - pass_len) - i)
                    buffer[i] = encoded[pos] if 0 <= pos < pass_len else self.PADDING_BYTE
                else:
                    buffer[i] = self.PADDING_BYTE

        except Exception as e:
            LogUtils.e(self.TAG, f"Password encoding error: {e}")
            return bytes(buffer)

        return bytes(buffer)

    def encode_username(self, username: str) -> bytes:
        """
        编码用户名

        将用户名字符串转换为固定长度(20字节)的ASCII表示。
        使用反向编码和ISO-8859-1编码。

        Args:
            username: 用户名字符串

        Returns:
            20字节的编码后用户名
        """
        buffer = bytearray(self.USERNAME_LENGTH)

        if not username:
            return bytes(buffer)

        try:
            encoded = username.encode('iso-8859-1')
            pad_len = self.USERNAME_LENGTH - len(encoded)

            for i in range(self.USERNAME_LENGTH):
                if i < pad_len:
                    buffer[i] = self.PADDING_BYTE
                else:
                    # 反向定位逻辑
                    pos = (len(encoded) - 1 + pad_len - i)
                    buffer[i] = encoded[pos] if 0 <= pos < len(encoded) else self.PADDING_BYTE

        except Exception as e:
            LogUtils.e(self.TAG, f"Username encoding error: {e}")
            return bytes(buffer)

    # 保持向后兼容的方法名
    get_ascii_password = encode_password
    get_ascii_username = encode_username
    get_check_byte = _calculate_checksum

    # endregion
