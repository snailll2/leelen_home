import time
import uuid


class BaseParam:
    def __init__(self, data=None, hash=None, value=None):
        self.data = data
        self.hash = hash
        self.value = value

    @property
    def data(self) -> str:
        return self._data

    @data.setter
    def data(self, value: str):
        self._data = value

    @property
    def hash(self) -> str:
        return self._hash

    @hash.setter
    def hash(self, value: str):
        self._hash = value

    @property
    def value(self) -> str:
        return self._value

    @value.setter
    def value(self, value: str):
        self._value = value

    def to_dict(self) -> dict:
        """将对象转换为可序列化的字典"""
        return {
            "data": self.data,
            "hash": self.hash,
            "value": self.value
        }


class GetVerifyCodeRequestParam:
    def __init__(self, username=None, verifyCodeType=12, verifyModel=1, intlPhoneCode=86, language="zh-CN"):
        self.username = username
        self.verifyCodeType = verifyCodeType
        self.verifyModel = verifyModel
        self.intlPhoneCode = intlPhoneCode
        self.language = language

    def to_dict(self) -> dict:
        """将对象转换为可序列化的字典"""
        return {
            "username": self.username,
            "verifyCodeType": self.verifyCodeType,
            "verifyModel": self.verifyModel,
            "intlPhoneCode": self.intlPhoneCode,
            "language": self.language,
        }


class ValidateVerifyCode:
    def __init__(self, username=None, verifyCode=None, verifyCodeSign=None, verifyCodeType=7, verifyModel=1,
                 intlPhoneCode=86):
        self.username = username
        self.verifyCode = verifyCode
        self.verifyCodeSign = verifyCodeSign
        self.verifyCodeType = verifyCodeType
        self.verifyModel = verifyModel
        self.intlPhoneCode = intlPhoneCode

    def to_dict(self) -> dict:
        """将对象转换为可序列化的字典"""
        return {
            "username": self.username,
            "verifyCode": self.verifyCode,
            "verifyCodeSign": self.verifyCodeSign,
            "verifyCodeType": self.verifyCodeType,
            "verifyModel": self.verifyModel,
            "intlPhoneCode": self.intlPhoneCode,
        }


class EncryptParam:
    timestamp = int(time.time() * 1000)
    uniqueCode = str(uuid.uuid4())

    def __init__(self):
        self.timestamp = int(time.time() * 1000)
        self.uniqueCode = str(uuid.uuid4())

    def to_dict(self) -> dict:
        """将对象转换为可序列化的字典"""
        return {
            "timestamp": self.timestamp,
            "uniqueCode": self.uniqueCode,
        }



class CodeLoginRequestParam(EncryptParam):
    Phone = ""
    username = ""
    verifyCode = ""
    verifyCodeSign = ""
    accountType = 1
    appVersion = "5.3.06"
    intlPhoneCode = 86
    osType = 2
    osVersion = "12"
    terminalId = "ANDROID-x"
    terminalModel = "REP-AN00"
    terminalName = "REP-AN00"


    def to_dict(self) -> dict:
        """将对象转换为可序列化的字典"""
        return {
            "timestamp": self.timestamp,
            "uniqueCode": self.uniqueCode,
            "phone": self.Phone,
            "accountType": self.accountType,
            "appVersion": self.appVersion,
            "intlPhoneCode": self.intlPhoneCode,
            "osType": self.osType,
            "osVersion": self.osVersion,
            "terminalId": self.terminalId,
            "terminalModel": self.terminalModel,
            "terminalName": self.terminalName,
            "username": self.username,
            "verifyCode": self.verifyCode,
            "verifyCodeSign": self.verifyCodeSign,
        }
