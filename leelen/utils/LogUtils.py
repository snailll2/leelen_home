import logging
import traceback


class LogUtils:
    """日志工具类 - 使用 Home Assistant 内置日志系统.

    日志级别可以通过 Home Assistant 的 configuration.yaml 控制:
    logger:
      logs:
        custom_components.leelen_home.leelen.utils.LogUtils: debug
    """

    # 使用标准 logging 格式，让 HA 控制格式
    logger = logging.getLogger(__name__)

    @classmethod
    def init_logger(cls):
        """初始化日志器 - 不再添加自定义 handler，由 HA 控制."""
        # 不添加任何 handler，让 HA 的日志配置接管
        # 保留此方法以保持向后兼容
        pass

    @staticmethod
    def d(tag, msg=""):
        """输出 DEBUG 级别日志."""
        LogUtils.logger.debug(f"[{tag}] {msg}", stacklevel=2)

    @staticmethod
    def v(tag, msg=""):
        """输出 INFO 级别日志 (verbose)."""
        LogUtils.logger.info(f"[{tag}] {msg}", stacklevel=2)

    @staticmethod
    def e(tag, msg=""):
        """输出 ERROR 级别日志."""
        # 打印异常跟踪信息到 stderr，然后记录错误日志
        traceback.print_exc()
        LogUtils.logger.error(f"[{tag}] {msg}", stacklevel=2)

    @staticmethod
    def w(tag, msg=""):
        """输出 WARNING 级别日志."""
        LogUtils.logger.warning(f"[{tag}] {msg}", stacklevel=2)

    @staticmethod
    def i(tag, msg=""):
        """输出 INFO 级别日志."""
        LogUtils.logger.info(f"[{tag}] {msg}", stacklevel=2)
