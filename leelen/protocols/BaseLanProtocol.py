"""
局域网协议基类

提供局域网通信协议的基础功能，包括：
- 协议数据解析
- 协议数据构建
- AES加密/解密
- 校验和计算

Classes:
    BaseLanProtocol: 局域网协议基类
"""

import threading
from typing import Optional, ClassVar
from dataclasses import dataclass, field

from ..common import LeelenConst, ProtocolDefault
from ..common.LeelenType import DeviceType
from ..entity.GatewayInfo import GatewayInfo
from ..utils.AesCoder import AesCoder
from ..utils.CRC8Utils import CRC8Utils
from ..utils.ConvertUtils import ConvertUtils
from ..utils.LogUtils import LogUtils
from ..utils.Exceptions import ProtocolException, safe_execute


@dataclass
class LanProtocolHeader:
    """
    局域网协议头结构

    Attributes:
        sync_header: 同步头 (4 bytes)
        length: 数据长度 (4 bytes)
        lan_protocol_ver: 协议版本 (2 bytes)
        source: 源地址 (8 bytes)
        dest: 目的地址 (8 bytes)
        server_id: 服务器ID (2 bytes)
        encrypted: 加密标志 (2 bytes)
        device_source: 设备源地址 (2 bytes)
        device_dest: 设备目的地址 (2 bytes)
        cmd: 命令 (2 bytes)
        frame_id: 帧ID (4 bytes)
        payload_type: 负载类型 (1 byte)
    """
    sync_header: bytes = field(default_factory=lambda: LeelenConst.LAN_SYNC_HEADER)
    length: int = 0
    lan_protocol_ver: bytes = field(default_factory=lambda: ProtocolDefault.PROTOCOL_VER_LAN)
    source: bytes = field(default_factory=lambda: bytes(8))
    dest: bytes = field(default_factory=lambda: bytes(8))
    server_id: bytes = field(default_factory=lambda: ProtocolDefault.DEFAULT_LAN_SERVER_ID)
    encrypted: bytes = field(default_factory=lambda: ProtocolDefault.LAN_NO_ENCRYPT)
    device_source: bytes = field(default_factory=lambda: bytes([0xFF, 0xFF]))
    device_dest: bytes = field(default_factory=lambda: bytes(2))
    cmd: bytes = field(default_factory=lambda: bytes(2))
    frame_id: bytes = field(default_factory=lambda: bytes(4))
    payload_type: bytes = field(default_factory=lambda: bytes([1]))

    # 常量
    HEAD_LENGTH: ClassVar[int] = 41
    HEAD_AND_LEN: ClassVar[int] = 8
    TAIL_LENGTH: ClassVar[int] = 1

    def to_bytes(self) -> bytes:
        """将头部转换为字节"""
        buffer = bytearray()
        buffer.extend(self.sync_header)
        buffer.extend(ConvertUtils.to_bytes(self.length, 'little'))
        buffer.extend(bytes([0, 0]))  # 保留字段
        buffer.extend(self.lan_protocol_ver)
        buffer.extend(self.source)
        buffer.extend(self.dest)
        buffer.extend(self.server_id)
        buffer.extend(self.encrypted)
        buffer.extend(self.device_source)
        buffer.extend(self.device_dest)
        buffer.extend(self.cmd)
        buffer.extend(self.frame_id)
        buffer.extend(bytes([0, 0]))  # 保留字段
        buffer.extend(self.payload_type)
        return bytes(buffer)


class BaseLanProtocol:
    """
    局域网协议基类

    提供LAN协议的基础功能，子类需要实现 build_body 方法。

    Attributes:
        TAG: 日志标签
        checksum: 校验和
        cmd: 命令字节
        frame_id: 帧ID
    """

    # 类级别的帧ID计数器和锁
    _frame_id: ClassVar[int] = 1
    _frame_lock: ClassVar[threading.Lock] = threading.Lock()

    # AES密钥（应该从配置读取）
    AES_KEY: ClassVar[str] = "h9sv5JUzjeJKW81z"
    AES_IV: ClassVar[str] = "9sng3f1cYsgQvEz5"

    def __init__(self):
        """初始化协议对象"""
        self.TAG = self.__class__.__name__

        # 头部相关
        self._header = LanProtocolHeader()
        self._is_add_sub = False

        # 数据部分
        self._request_data: Optional[bytes] = None
        self._request_data_body: Optional[bytes] = None
        self._request_data_head: Optional[bytes] = None
        self.checksum: int = 0

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
    def frame_id(self) -> Optional[bytes]:
        """获取帧ID"""
        return self._header.frame_id

    @property
    def source(self) -> bytes:
        """获取源地址"""
        return self._header.source

    @property
    def dest(self) -> bytes:
        """获取目的地址"""
        return self._header.dest

    @dest.setter
    def dest(self, value: bytes) -> None:
        """设置目的地址"""
        self._header.dest = value
    
    

    @property
    def server_id(self) -> bytes:
        """获取服务器ID"""
        return self._header.server_id

    @server_id.setter
    def server_id(self, value: bytes) -> None:
        """设置服务器ID"""
        self._header.server_id = value

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

    @property
    def encrypted(self) -> bytes:
        """获取加密标志"""
        return self._header.encrypted

    @encrypted.setter
    def encrypted(self, value: bytes) -> None:
        """设置加密标志"""
        self._header.encrypted = value

    @property
    def device_dest(self) -> bytes:
        """获取设备目的地址"""
        return self._header.device_dest

    @device_dest.setter
    def device_dest(self, value: bytes) -> None:
        """设置设备目的地址"""
        self._header.device_dest = value
    
    @property
    def device_source(self) -> bytes:
        """获取设备源地址"""
        return self._header.device_source

    @device_source.setter
    def device_source(self, value: bytes) -> None:
        """设置设备源地址"""
        self._header.device_source = value
    
    @property
    def payload_type(self) -> bytes:
        """获取有效类型"""
        return self._header.payload_type

    @payload_type.setter
    def payload_type(self, value: bytes) -> None:
        """设置有效类型"""
        self._header.payload_type = value
    
    @property
    def lan_protocol_ver(self) -> bytes:
        """获取LAN协议版本"""
        return self._header.lan_protocol_ver
    
    @lan_protocol_ver.setter
    def lan_protocol_ver(self, value: bytes) -> None:
        """设置LAN协议版本"""
        self._header.lan_protocol_ver = value

    # endregion

    # region 静态方法

    @staticmethod
    def get_aes_real_body(data: bytes) -> bytes:
        """
        解密AES数据并提取实际内容

        Args:
            data: 加密的数据

        Returns:
            解密后的实际内容
        """
        decrypted = AesCoder.get_instance().decrypt(
            BaseLanProtocol.AES_KEY,
            BaseLanProtocol.AES_IV,
            data
        )
        buffer = memoryview(decrypted)
        length = ConvertUtils.to_unsigned_short(buffer[0:2])
        return bytes(buffer[2:2 + length])

    @classmethod
    def get_frame_id(cls) -> int:
        """
        获取下一个帧ID

        Returns:
            递增的帧ID（1-65535循环）
        """
        with cls._frame_lock:
            if cls._frame_id >= 65535:
                cls._frame_id = 1
            frame_id = cls._frame_id
            cls._frame_id += 1
            return frame_id

    @classmethod
    def parse(cls, data: bytes) -> Optional['BaseLanProtocol']:
        """
        解析协议数据

        Args:
            data: 原始协议数据

        Returns:
            解析后的协议对象，失败返回None
        """
        if not data:
            LogUtils.e("BaseLanProtocol", "Data is null")
            return None

        if len(data) == 0:
            LogUtils.e("BaseLanProtocol", "Data length is 0")
            return None

        if len(data) < LanProtocolHeader.HEAD_LENGTH + 1:
            LogUtils.e(
                "BaseLanProtocol",
                f"Data length {len(data)} < minimum required"
            )
            return None

        try:
            protocol = cls()
            buffer = memoryview(data)

            # 解析头部
            header = LanProtocolHeader()
            header.sync_header = bytes(buffer[0:4])
            header.length = ConvertUtils.to_int(buffer[4:8])
            header.lan_protocol_ver = bytes(buffer[8:10])
            header.source = bytes(buffer[10:18])
            header.dest = bytes(buffer[18:26])
            header.server_id = bytes(buffer[26:28])
            header.encrypted = bytes(buffer[28:30])
            header.device_source = bytes(buffer[30:32])
            header.device_dest = bytes(buffer[32:34])
            header.cmd = bytes(buffer[34:36])
            header.frame_id = bytes(buffer[36:40])
            header.payload_type = bytes(buffer[40:41])

            protocol._header = header

            # 计算并提取数据体
            body_len = (
                header.length +
                header.HEAD_AND_LEN -
                header.HEAD_LENGTH -
                header.TAIL_LENGTH
            )
            protocol._request_data_body = bytes(
                buffer[header.HEAD_LENGTH:header.HEAD_LENGTH + body_len]
            )

            # 如果需要解密
            if header.encrypted != bytes([0, 0]):
                protocol._request_data_body = cls.get_aes_real_body(
                    protocol._request_data_body
                )

            # 校验和
            protocol.checksum = buffer[header.HEAD_LENGTH + body_len]
            protocol._request_data = data

            return protocol

        except Exception as e:
            LogUtils.e("BaseLanProtocol", f"Parse error: {e}")
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

    def _build_head(
        self,
        source: bytes,
        dest: bytes,
        device_dest: bytes
    ) -> bool:
        """
        构建协议头

        Args:
            source: 源地址
            dest: 目的地址
            device_dest: 设备目的地址

        Returns:
            构建是否成功
        """
        try:
            self._header.source = source
            self._header.dest = dest
            self._header.device_dest = device_dest

            # 计算长度
            self._header.length = (
                LanProtocolHeader.HEAD_LENGTH -
                LanProtocolHeader.HEAD_AND_LEN +
                LanProtocolHeader.TAIL_LENGTH
            )
            if self._request_data_body:
                self._header.length += len(self._request_data_body)

            # 设置服务器ID
            gateway_info = GatewayInfo.get_instance()
            if self._is_add_sub:
                self._header.server_id = gateway_info.get_sub_tcp_server_code()
                self._header.device_source = gateway_info.get_sub_tcp_server_code()
            else:
                self._header.server_id = gateway_info.get_tcp_server_code()
                self._header.device_source = gateway_info.get_tcp_server_code()

            # 设置帧ID
            self._header.frame_id = ConvertUtils.to_bytes(self.get_frame_id())

            # 生成头部字节
            self._request_data_head = self._header.to_bytes()
            return True

        except Exception as e:
            LogUtils.e(self.TAG, f"Build head error: {e}")
            return False

    def _encrypt_body(self) -> bool:
        """
        加密数据体

        Returns:
            加密是否成功
        """
        if not self._request_data_body:
            return True

        if self._header.encrypted == bytes([0, 0]):
            return True

        try:
            body_len = len(self._request_data_body)
            len_bytes = ConvertUtils.to_bytes(body_len)

            buffer = bytearray()
            buffer.extend(len_bytes)
            buffer.extend(self._request_data_body)

            self._request_data_body = AesCoder.get_instance().encrypt(
                self.AES_KEY,
                self.AES_IV,
                bytes(buffer)
            )
            return True

        except Exception as e:
            LogUtils.e(self.TAG, f"Encrypt body error: {e}")
            return False

    def get_request_data(
        self,
        source: bytes = bytes(8),
        dest: bytes = bytes(8),
        device_dest: bytes = bytes(2)
    ) -> Optional[bytes]:
        """
        获取完整的请求数据

        Args:
            source: 源地址 (8 bytes)
            dest: 目的地址 (8 bytes)
            device_dest: 设备目的地址 (2 bytes)

        Returns:
            完整的协议数据，失败返回None
        """
        # 构建数据体
        if not self.build_body():
            LogUtils.e(self.TAG, "Build body failed")
            return None

        # 加密数据体
        if not self._encrypt_body():
            LogUtils.e(self.TAG, "Encrypt body failed")
            return None

        # 处理默认设备目的地址
        if device_dest is None:
            device_dest = bytes([0, 0])

        # 构建头部
        if not self._build_head(source, dest, device_dest):
            LogUtils.e(self.TAG, "Build head failed")
            return None

        # 组装数据并计算校验和
        buffer = bytearray()
        buffer.extend(self._request_data_head)
        if self._request_data_body:
            buffer.extend(self._request_data_body)

        self.checksum = CRC8Utils.calc_shift_val(buffer, len(buffer))
        buffer.append(self.checksum)

        return bytes(buffer)

    # endregion
