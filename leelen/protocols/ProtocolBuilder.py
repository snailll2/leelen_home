"""
协议构建器模块

提供统一的协议数据构建接口，简化协议类的实现。
"""

from abc import ABC, abstractmethod
from typing import Optional, Callable
from dataclasses import dataclass, field

from ..utils.LogUtils import LogUtils
from ..utils.Exceptions import safe_execute, ProtocolException


@dataclass
class ProtocolField:
    """
    协议字段定义

    Attributes:
        name: 字段名
        length: 字段长度（字节）
        default: 默认值
        validator: 验证函数
    """
    name: str
    length: int
    default: bytes = field(default_factory=bytes)
    validator: Optional[Callable[[bytes], bool]] = None


class ProtocolBuilder(ABC):
    """
    协议构建器基类

    提供统一的协议数据构建流程：
    1. build_head - 构建协议头
    2. build_body - 构建协议体
    3. build_tail - 构建协议尾
    4. validate - 验证数据完整性

    Example:
        class MyProtocol(ProtocolBuilder):
            def __init__(self):
                super().__init__()
                self.fields = [
                    ProtocolField("cmd", 2, b'\\x00\\x01'),
                    ProtocolField("data", 4)
                ]

            def build_body(self) -> bytes:
                # 实现具体的协议体构建逻辑
                return self._encode_fields()
    """

    def __init__(self, tag: Optional[str] = None):
        """
        初始化协议构建器

        Args:
            tag: 日志标签，默认为类名
        """
        self.tag = tag or self.__class__.__name__
        self.fields: list[ProtocolField] = []
        self._field_values: dict[str, bytes] = {}
        self._head: bytes = b''
        self._body: bytes = b''
        self._tail: bytes = b''
        self._built: bool = False

    def set_field(self, name: str, value: bytes) -> 'ProtocolBuilder':
        """
        设置字段值

        Args:
            name: 字段名
            value: 字段值

        Returns:
            self，支持链式调用

        Raises:
            ProtocolException: 字段验证失败
        """
        field = self._get_field(name)
        if field is None:
            raise ProtocolException(f"Unknown field: {name}")

        if len(value) != field.length:
            raise ProtocolException(
                f"Field '{name}' length mismatch: "
                f"expected {field.length}, got {len(value)}"
            )

        if field.validator and not field.validator(value):
            raise ProtocolException(f"Field '{name}' validation failed")

        self._field_values[name] = value
        return self

    def get_field(self, name: str) -> bytes:
        """
        获取字段值

        Args:
            name: 字段名

        Returns:
            字段值

        Raises:
            ProtocolException: 字段不存在
        """
        if name not in self._field_values:
            field = self._get_field(name)
            if field:
                return field.default
            raise ProtocolException(f"Field '{name}' not set")
        return self._field_values[name]

    def _get_field(self, name: str) -> Optional[ProtocolField]:
        """获取字段定义"""
        for field in self.fields:
            if field.name == name:
                return field
        return None

    def _encode_fields(self) -> bytes:
        """
        编码所有字段

        Returns:
            编码后的字节数据
        """
        buffer = bytearray()
        for field in self.fields:
            value = self._field_values.get(field.name, field.default)
            buffer.extend(value)
        return bytes(buffer)

    @abstractmethod
    def build_head(self) -> bytes:
        """
        构建协议头

        Returns:
            协议头字节数据
        """
        pass

    @abstractmethod
    def build_body(self) -> bytes:
        """
        构建协议体

        Returns:
            协议体字节数据
        """
        pass

    def build_tail(self) -> bytes:
        """
        构建协议尾

        Returns:
            协议尾字节数据
        """
        return b''

    def validate(self) -> bool:
        """
        验证协议数据

        Returns:
            验证是否通过
        """
        return True

    @safe_execute(default_return=None, error_message="Build failed")
    def build(self) -> Optional[bytes]:
        """
        构建完整协议数据

        Returns:
            完整的协议数据，构建失败返回None
        """
        if self._built:
            LogUtils.w(self.tag, "Protocol already built, rebuilding...")

        # 构建各部分
        self._head = self.build_head()
        if self._head is None:
            LogUtils.e(self.tag, "Build head failed")
            return None

        self._body = self.build_body()
        if self._body is None:
            LogUtils.e(self.tag, "Build body failed")
            return None

        self._tail = self.build_tail()

        # 验证
        if not self.validate():
            LogUtils.e(self.tag, "Validation failed")
            return None

        # 组合数据
        buffer = bytearray()
        buffer.extend(self._head)
        buffer.extend(self._body)
        buffer.extend(self._tail)

        self._built = True
        return bytes(buffer)

    def reset(self) -> 'ProtocolBuilder':
        """
        重置构建器状态

        Returns:
            self，支持链式调用
        """
        self._field_values.clear()
        self._head = b''
        self._body = b''
        self._tail = b''
        self._built = False
        return self


class FixedLengthProtocolBuilder(ProtocolBuilder):
    """
    固定长度协议构建器

    适用于长度固定的协议格式。
    """

    def __init__(self, total_length: int, tag: Optional[str] = None):
        """
        初始化

        Args:
            total_length: 协议总长度
            tag: 日志标签
        """
        super().__init__(tag)
        self.total_length = total_length

    def validate(self) -> bool:
        """验证总长度"""
        total = len(self._head) + len(self._body) + len(self._tail)
        if total != self.total_length:
            LogUtils.e(
                self.tag,
                f"Length mismatch: expected {self.total_length}, got {total}"
            )
            return False
        return True


class VariableLengthProtocolBuilder(ProtocolBuilder):
    """
    变长协议构建器

    适用于长度可变的协议格式，自动计算并填充长度字段。
    """

    def __init__(
        self,
        length_field: str,
        length_offset: int = 0,
        length_size: int = 4,
        tag: Optional[str] = None
    ):
        """
        初始化

        Args:
            length_field: 长度字段名
            length_offset: 长度偏移量（用于计算长度时的调整）
            length_size: 长度字段大小（字节）
            tag: 日志标签
        """
        super().__init__(tag)
        self.length_field = length_field
        self.length_offset = length_offset
        self.length_size = length_size

    def _calculate_length(self) -> int:
        """计算协议总长度"""
        return len(self._head) + len(self._body) + len(self._tail) + self.length_offset

    def build(self) -> Optional[bytes]:
        """构建协议，自动设置长度字段"""
        # 先构建body以获取长度
        self._body = self.build_body()
        if self._body is None:
            return None

        # 计算并设置长度
        length = self._calculate_length()
        length_bytes = length.to_bytes(self.length_size, 'little')
        self.set_field(self.length_field, length_bytes)

        # 继续正常构建流程
        return super().build()


class ChecksumProtocolBuilder(ProtocolBuilder):
    """
    带校验和的协议构建器

    自动计算并填充校验和。
    """

    def __init__(
        self,
        checksum_func: Callable[[bytes], int],
        checksum_size: int = 1,
        tag: Optional[str] = None
    ):
        """
        初始化

        Args:
            checksum_func: 校验和计算函数
            checksum_size: 校验和大小（字节）
            tag: 日志标签
        """
        super().__init__(tag)
        self.checksum_func = checksum_func
        self.checksum_size = checksum_size

    def build_tail(self) -> bytes:
        """构建尾部，包含校验和"""
        data = self._head + self._body
        checksum = self.checksum_func(data)
        return checksum.to_bytes(self.checksum_size, 'little')
