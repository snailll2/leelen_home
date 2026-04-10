from typing import Optional


class LoginReq:
    def __init__(self):
        self.DUID: Optional[str] = None  # Device Unique ID
        self.dev_type: int = 0  # Device type(integer)
        self.random: Optional[str] = None  # Random string/nonce
        self.user: Optional[str] = None  # Username or user identifier
        self.user_type: int = 0  # User type(integer)

    def __str__(self) -> str:
        return (f"LoginReq(DUID='{self.DUID}', dev_type={self.dev_type}, "
                f"random='{self.random}', user='{self.user}', "
                f"user_type={self.user_type})")

    def __repr__(self) -> str:
        return self.__str__()

    def to_dict(self) -> dict:
        """将对象转换为可序列化的字典"""
        return {
            "DUID": self.DUID,
            "dev_type": self.dev_type,
            "random": self.random,
            "user": self.user,
            "user_type": self.user_type,
        }
