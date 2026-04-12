"""Logging utilities for Leelen integration."""
import logging

_LOGGER = logging.getLogger(__name__)


class LogUtils:
    """日志工具类 - 使用 Home Assistant 内置日志系统."""

    @staticmethod
    def d(tag: str, msg: str = "") -> None:
        """输出 DEBUG 级别日志."""
        _LOGGER.debug("[%s] %s", tag, msg)

    @staticmethod
    def v(tag: str, msg: str = "") -> None:
        """输出 INFO 级别日志 (verbose)."""
        _LOGGER.info("[%s] %s", tag, msg)

    @staticmethod
    def e(tag: str, msg: str = "") -> None:
        """输出 ERROR 级别日志."""
        _LOGGER.error("[%s] %s", tag, msg, exc_info=True)

    @staticmethod
    def w(tag: str, msg: str = "") -> None:
        """输出 WARNING 级别日志."""
        _LOGGER.warning("[%s] %s", tag, msg)

    @staticmethod
    def i(tag: str, msg: str = "") -> None:
        """输出 INFO 级别日志."""
        _LOGGER.info("[%s] %s", tag, msg)
