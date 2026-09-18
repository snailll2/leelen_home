"""Logging utilities for Leelen integration."""
import inspect
import logging
import sys

# 各类调用共享同一目标?否——每条日志发到「调用方模块」自己的 logger,
# 使 HA logger 集成能按 logger 层级(前缀)分模块设级别,例如:
#   logger:
#     custom_components.leelen_home.leelen.models: debug
#     custom_components.leelen_home.switch: warning

# 是否在每条日志末尾追加实际调用位置 `文件名:行号 函数名`。
LOG_SHOW_CALLER_LOCATION = True


class LogUtils:
    """日志工具类 - 基于 HA 内置日志系统.

    - 每条日志归属「调用方模块」的 logger(经帧解析),而非本模块固定 logger;
      这样 HA `logger:` 配置能按模块前缀命中不同级别。
    - HA 全局日志格式固定不含文件名/行号,故把调用位置拼进消息尾部。
    """

    @staticmethod
    def _emit(level: int, tag: str, msg: str, exc_info: bool = False) -> None:
        """解析调用方模块与调用位置,再发给该模块的 logger。

        帧链:业务调用方 ← d/i/v/w/e ← _emit(currentframe)。
        """
        frame = None
        try:
            frame = inspect.currentframe()
            caller = frame.f_back.f_back  # 跳过静态方法:业务调用方
            modname = caller.f_globals.get("__name__", "")
            logger = logging.getLogger(modname) if modname else logging.getLogger(__name__)
            if not logger.isEnabledFor(level):
                return
            prefix = ""
            if LOG_SHOW_CALLER_LOCATION:
                path = caller.f_code.co_filename.replace("\\", "/").split("/")[-1]
                prefix = f"({path}:{caller.f_lineno} {caller.f_code.co_name}) "
            # 位置放行首;开关关闭时按旧格式 [tag] msg,不带多余前导空格
            full = f"{prefix}[{tag}] {msg}" if prefix else f"[{tag}] {msg}"
            logger.log(level, "%s", full, exc_info=exc_info)
        except Exception:
            # 帧解析失败时降级:仍发日志,只是归到本模块 ylogger、不带位置
            logging.getLogger(__name__).log(
                level, "[%s] %s", tag, msg, exc_info=exc_info
            )
        finally:
            if frame is not None:
                del frame

    @staticmethod
    def d(tag: str, msg: str = "", *, exc_info: bool = False) -> None:
        """输出 DEBUG 级别日志."""
        LogUtils._emit(logging.DEBUG, tag, msg, exc_info=exc_info)

    @staticmethod
    def v(tag: str, msg: str = "", *, exc_info: bool = False) -> None:
        """输出 INFO 级别日志 (verbose)."""
        LogUtils._emit(logging.INFO, tag, msg, exc_info=exc_info)

    @staticmethod
    def e(tag: str, msg: str = "", *, exc_info: bool | None = None) -> None:
        """输出 ERROR 级别日志。

        ``exc_info`` 默认 ``None`` = **自动判定**:当前正在处理异常(即调用点位于
        except 块内)就附上堆栈,否则不附。这样两头都不会踩:

        - 纯消息(本项目 26 处,如 "data is null")不再被 logging 打印一行无意义的
          ``NoneType: None`` —— 那是原先硬编码 exc_info=True 的产物;
        - 在 except 里记录时自动带上 traceback,不会因为忘了传参而丢掉堆栈。

        需要强制时显式传 ``True``/``False``(现有异常记录点大多显式传了 True,
        既表明意图,也能防止日志调用日后被挪出 except 块后悄悄丢堆栈)。
        """
        if exc_info is None:
            exc_info = sys.exc_info()[0] is not None
        LogUtils._emit(logging.ERROR, tag, msg, exc_info=exc_info)

    @staticmethod
    def w(tag: str, msg: str = "", *, exc_info: bool = False) -> None:
        """输出 WARNING 级别日志."""
        LogUtils._emit(logging.WARNING, tag, msg, exc_info=exc_info)

    @staticmethod
    def i(tag: str, msg: str = "", *, exc_info: bool = False) -> None:
        """输出 INFO 级别日志."""
        LogUtils._emit(logging.INFO, tag, msg, exc_info=exc_info)
