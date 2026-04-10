"""
工具模块

提供项目所需的各种工具函数和类。

Modules:
    AesCoder: AES加密/解密
    Base64Utils: Base64编码/解码
    ConvertUtils: 数据类型转换
    CRC8Utils: CRC8校验
    DataPkgUtils: 数据包处理
    EncodeUtil: 编码工具
    Exceptions: 异常处理
    LogUtils: 日志工具
    RSAEncrypt: RSA加密
    Singleton: 单例模式
    SslUtils: SSL/TLS工具
    TlvUtils: TLV编码
"""

from .AesCoder import AesCoder
from .Base64Utils import Base64Utils
from .ConvertUtils import ConvertUtils
from .CRC8Utils import CRC8Utils
from .DataPkgUtils import DataPkgUtils
from .EncodeUtil import EncodeUtil
from .Exceptions import (
    LeelenException,
    NetworkException,
    ConnectionException,
    ProtocolException,
    EncryptionException,
    ValidationException,
    ErrorCode,
    safe_execute,
    retry_on_error,
    validate_param,
    handle_exceptions,
)
from .LogUtils import LogUtils
from .RSAEncrypt import RSAEncrypt
from .Singleton import (
    singleton,
    SingletonMeta,
    SingletonBase,
    thread_safe_lazy_init,
)
from .SslUtils import SslUtils
from .TlvUtils import TlvUtils

__all__ = [
    # 类
    'AesCoder',
    'Base64Utils',
    'ConvertUtils',
    'CRC8Utils',
    'DataPkgUtils',
    'EncodeUtil',
    'LeelenException',
    'NetworkException',
    'ConnectionException',
    'ProtocolException',
    'EncryptionException',
    'ValidationException',
    'ErrorCode',
    'LogUtils',
    'RSAEncrypt',
    'SslUtils',
    'TlvUtils',
    'SingletonMeta',
    'SingletonBase',
    # 装饰器/函数
    'safe_execute',
    'retry_on_error',
    'validate_param',
    'handle_exceptions',
    'singleton',
    'thread_safe_lazy_init',
]
