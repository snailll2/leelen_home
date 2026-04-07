import threading

from ..common import WanProtocolCmd
from ..protocols.BaseWanProtocol import BaseWanProtocol
from ..utils.ConvertUtils import ConvertUtils
from ..utils.LogUtils import LogUtils


class LoginWanProtocol(BaseWanProtocol):
    APP_PWD_LENGTH = 32
    APP_USER_LENGTH = 20
    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        super().__init__()
        self.TAG = self.__class__.__name__
        self.app_pwd = None
        self.app_user = None
        self.logon_mark = bytes([0xFF, 0xFF])
        self.cmd = WanProtocolCmd.APP_LOGON

    @classmethod
    def get_instance(cls):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = LoginWanProtocol()
        return cls._instance

    def build_body(self) -> bool:
        if not self.app_user or len(self.app_user) != self.APP_USER_LENGTH:
            LogUtils.e(self.TAG, "field 'appUser' invalid.")
            return False

        if not self.app_pwd or len(self.app_pwd) != self.APP_PWD_LENGTH:
            LogUtils.e(self.TAG, "field 'appPwd' invalid.")
            return False

        buffer = bytearray()
        buffer.extend(self.app_user)
        buffer.extend(self.app_pwd)


        self.request_data_body = bytes(buffer)
        return True

    def build_tail(self) -> None:
        buffer = bytearray()
        self.checksum = self.get_check_byte(self.request_data_head, self.request_data_body, self.logon_mark)
        buffer.extend(self.logon_mark)
        buffer.append(self.checksum)
        self.request_data_tail = bytes(buffer)

    def set_app_pwd(self, pwd: str) -> None:
        self.app_pwd = self.get_ascii_password(pwd)

    def set_app_user(self, user: str) -> None:
        self.app_user = self.get_ascii_username(user)

    def set_logon_mark(self, mark: int) -> None:
        self.logon_mark = ConvertUtils.to_bytes(mark)
