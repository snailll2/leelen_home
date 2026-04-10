"""
异常处理工具模块

提供统一的异常处理机制和自定义异常类。
"""

from enum import IntEnum
from typing import Optional, Callable, Any, TypeVar
from functools import wraps

from .LogUtils import LogUtils

T = TypeVar('T')


class ErrorCode(IntEnum):
    """错误码枚举"""
    SUCCESS = 0
    UNKNOWN_ERROR = 1000
    NETWORK_ERROR = 1001
    CONNECTION_ERROR = 1002
    TIMEOUT_ERROR = 1003
    AUTH_ERROR = 1004
    INVALID_PARAM = 1005
    PROTOCOL_ERROR = 1006
    ENCRYPTION_ERROR = 1007
    SOCKET_ERROR = 1008
    DATA_PARSE_ERROR = 1009
    NOT_INITIALIZED = 1010


class LeelenException(Exception):
    """
    基础异常类

    Attributes:
        error_code: 错误码
        message: 错误信息
        details: 详细错误信息
    """

    def __init__(
        self,
        message: str,
        error_code: ErrorCode = ErrorCode.UNKNOWN_ERROR,
        details: Optional[str] = None
    ):
        super().__init__(message)
        self.error_code = error_code
        self.message = message
        self.details = details

    def __str__(self) -> str:
        if self.details:
            return f"[{self.error_code.name}] {self.message} - {self.details}"
        return f"[{self.error_code.name}] {self.message}"


class NetworkException(LeelenException):
    """网络相关异常"""
    def __init__(self, message: str, details: Optional[str] = None):
        super().__init__(message, ErrorCode.NETWORK_ERROR, details)


class ConnectionException(LeelenException):
    """连接相关异常"""
    def __init__(self, message: str, details: Optional[str] = None):
        super().__init__(message, ErrorCode.CONNECTION_ERROR, details)


class ProtocolException(LeelenException):
    """协议相关异常"""
    def __init__(self, message: str, details: Optional[str] = None):
        super().__init__(message, ErrorCode.PROTOCOL_ERROR, details)


class EncryptionException(LeelenException):
    """加密相关异常"""
    def __init__(self, message: str, details: Optional[str] = None):
        super().__init__(message, ErrorCode.ENCRYPTION_ERROR, details)


class ValidationException(LeelenException):
    """数据验证异常"""
    def __init__(self, message: str, details: Optional[str] = None):
        super().__init__(message, ErrorCode.INVALID_PARAM, details)


def safe_execute(
    default_return: Optional[T] = None,
    error_message: str = "Operation failed",
    log_tag: str = "safe_execute"
) -> Callable:
    """
    安全执行装饰器

    捕获异常并记录日志，返回默认值。

    Args:
        default_return: 发生异常时的默认返回值
        error_message: 错误日志消息
        log_tag: 日志标签

    Returns:
        装饰器函数
    """
    def decorator(func: Callable[..., T]) -> Callable[..., Optional[T]]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Optional[T]:
            try:
                return func(*args, **kwargs)
            except LeelenException as e:
                LogUtils.e(log_tag, f"{error_message}: {e}")
                return default_return
            except Exception as e:
                LogUtils.e(log_tag, f"{error_message}: Unexpected error - {e}")
                return default_return
        return wrapper
    return decorator


def retry_on_error(
    max_retries: int = 3,
    delay: float = 1.0,
    exceptions: tuple = (Exception,),
    on_retry: Optional[Callable[[int, Exception], None]] = None
) -> Callable:
    """
    重试装饰器

    在指定异常发生时进行重试。

    Args:
        max_retries: 最大重试次数
        delay: 重试间隔（秒）
        exceptions: 需要重试的异常类型
        on_retry: 每次重试时的回调函数

    Returns:
        装饰器函数
    """
    import time

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            last_exception = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_retries:
                        if on_retry:
                            on_retry(attempt + 1, e)
                        time.sleep(delay)
            raise last_exception
        return wrapper
    return decorator


def validate_param(
    condition: Callable[[Any], bool],
    param_name: str,
    error_message: str
) -> None:
    """
    参数验证函数

    Args:
        condition: 验证条件
        param_name: 参数名
        error_message: 错误消息

    Raises:
        ValidationException: 验证失败时抛出
    """
    if not condition:
        raise ValidationException(
            f"Invalid parameter '{param_name}'",
            error_message
        )


class ExceptionHandler:
    """
    异常处理器

    提供统一的异常处理入口。
    """

    _instance: Optional['ExceptionHandler'] = None
    _handlers: dict[ErrorCode, list[Callable[[LeelenException], None]]] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def get_instance(cls) -> 'ExceptionHandler':
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def register_handler(
        self,
        error_code: ErrorCode,
        handler: Callable[[LeelenException], None]
    ) -> None:
        """
        注册异常处理器

        Args:
            error_code: 错误码
            handler: 处理函数
        """
        if error_code not in self._handlers:
            self._handlers[error_code] = []
        self._handlers[error_code].append(handler)

    def handle(self, exception: LeelenException) -> None:
        """
        处理异常

        Args:
            exception: 需要处理的异常
        """
        LogUtils.e("ExceptionHandler", str(exception))

        handlers = self._handlers.get(exception.error_code, [])
        for handler in handlers:
            try:
                handler(exception)
            except Exception as e:
                LogUtils.e("ExceptionHandler", f"Handler error: {e}")


def handle_exceptions(
    error_code: ErrorCode = ErrorCode.UNKNOWN_ERROR,
    log_tag: str = "handle_exceptions",
    reraise: bool = False
) -> Callable:
    """
    统一异常处理装饰器

    Args:
        error_code: 错误码
        log_tag: 日志标签
        reraise: 是否重新抛出异常

    Returns:
        装饰器函数
    """
    def decorator(func: Callable[..., T]) -> Callable[..., Optional[T]]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Optional[T]:
            try:
                return func(*args, **kwargs)
            except LeelenException:
                if reraise:
                    raise
                return None
            except Exception as e:
                LogUtils.e(log_tag, f"Error in {func.__name__}: {e}")
                if reraise:
                    raise LeelenException(str(e), error_code)
                return None
        return wrapper
    return decorator
