from typing import Optional


class User:
    """登录用户运行时状态 —— 纯数据持有,字段即状态,直接属性读写。

    遗留:Java getter/setter 包装(get_*/set_*)已清除,改为属性访问。
    保留 is_project_account() 派生方法(判断是否为项目账号)。
    """

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