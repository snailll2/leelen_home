import logging
from typing import Optional

from ..utils.LogUtils import LogUtils


class User:
    TAG = "User"
    _instance: Optional['User'] = None

    def __init__(self):
        self.account_id = -1
        self.had_update = False
        self.is_login_lan = False
        self.is_main_account = False
        self.login_status = False
        self.password = ""
        self.sound_type = ""
        self.username = ""

    @classmethod
    def get_instance(cls) -> 'User':
        if not cls._instance:
            cls._instance = User()
        return cls._instance

    def get_account_id(self) -> int:
        return self.account_id

    def get_is_login_lan(self) -> bool:
        return self.is_login_lan

    def get_password(self) -> str:
        return self.password

    def get_sound_type(self) -> str:
        return self.sound_type

    def get_username(self) -> str:
        return self.username

    def is_login(self) -> bool:
        logging.debug(f"{self.TAG} isLogin() login status: {self.login_status}")
        return self.login_status

    def is_main_account(self) -> bool:
        return self.is_main_account

    def is_project_account(self) -> bool:
        return self.username == "leelen"

    def reset(self):
        self.username = ""
        self.password = ""
        self.sound_type = ""
        self.account_id = -1
        self.login_status = False
        self.had_update = False

    def save(self):
        pass

    def set_account_id(self, account_id: int):
        LogUtils.d(f"{self.TAG} setAccountId() account id: {account_id}")
        self.account_id = account_id

    def set_is_login_lan(self, is_login: bool):
        self.is_login_lan = is_login

    def set_is_main_account(self, is_main: bool):
        self.is_main_account = is_main

    def set_login_status(self, status: bool):
        self.login_status = status

    def set_password(self, password: str):
        self.password = password

    def set_sound_type(self, sound_type: str):
        self.sound_type = sound_type

    def set_username(self, username: str):
        self.username = username
