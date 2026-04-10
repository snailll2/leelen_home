import logging
import traceback


class LogUtils:
    LOG_FILE_PATTERN = "[%(asctime)s] [%(levelname)s] [%(filename)s:%(lineno)d] - %(message)s"
    save_to_file = False
    use_logcat = True
    logger = logging.getLogger(__name__)
    

    @classmethod
    def init_logger(cls):
        # 删除所有已存在的Handler
        for handler in cls.logger.handlers[:]:
            cls.logger.removeHandler(handler)
            handler.close()
        formatter = logging.Formatter(cls.LOG_FILE_PATTERN)
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        cls.logger.addHandler(console_handler)
        # cls.logger.setLevel(logging.INFO)
        cls.logger.setLevel(logging.DEBUG)

    @staticmethod
    def d(tag, msg=""):
        if LogUtils.use_logcat:
            LogUtils.logger.debug(f"{tag} -> {msg}", stacklevel=2)

    @staticmethod
    def v(tag, msg=""):
        if LogUtils.use_logcat:
            LogUtils.logger.info(f"{tag} -> {msg}", stacklevel=2)

    @staticmethod
    def e(tag, msg=""):
        if LogUtils.use_logcat:
            traceback.print_exc()
            LogUtils.logger.error(f"{tag} -> {msg}", stacklevel=2)

    @staticmethod
    def w(tag, msg=""):
        if LogUtils.use_logcat:
            LogUtils.logger.warning(f"{tag} -> {msg}", stacklevel=2)

    @staticmethod
    def i(tag, msg=""):
        if LogUtils.use_logcat:
            LogUtils.logger.info(f"{tag} -> {msg}", stacklevel=2)


# 只需调用一次，初始化日志系统
LogUtils.init_logger()
