import os
import hashlib
import json
import random
import string
import threading
import time
import uuid
from typing import Any

import aiofiles as aiofiles
import aiohttp
import aiosqlite
from aiohttp import ClientError
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from ..entity.BaseParam import BaseParam, CodeLoginRequestParam, GetVerifyCodeRequestParam
from ..entity.BaseRequest import BaseRequest
# from ..process import get_secret
from ..utils.AesCoder import AesCoder
from ..utils.LogUtils import LogUtils
from ..utils.RSAEncrypt import RSAEncrypt


class HttpApi:
    _instance = None
    _lock = threading.Lock()

    def __init__(self, hass: HomeAssistant):
        # pass
        self.BASE_URL = "https://iot.leelen.com"
        self.RD_BASE_URL = "https://rd.iot.leelen.com"
        self.device_addr = ""
        self.appTerminalId = f"ANDROID-{self.get_terminal_id()}"
        self.appTerminalModel = "REP-AN00"
        self.uuid = None
        self.verifyCodeSign = ""
        self.username = ""
        self._hass = hass
        self._device_list = []

    def get_secret(self, num: int) -> str:
        chars = string.ascii_letters + string.digits  # equivalent to "abcdef...6789"
        return ''.join(random.choice(chars) for _ in range(num))


    @classmethod
    def get_instance(cls, hass: HomeAssistant = None):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = HttpApi(hass)
        return cls._instance

    def get_terminal_id(self):
        return hashlib.md5(''.join(random.choices(string.ascii_letters + string.digits, k=32)).encode()).hexdigest()

    async def get_user(self, accessToken):
        session = async_get_clientsession(self._hass)
        headers = {
            "Authorization": f"Bearer {accessToken}"
        }
        async with session.post(
                f"{self.BASE_URL}/rest/app/community/platform/getUser",
                verify_ssl=False,
                headers=headers,
                json={
                },
        ) as res:
            res.raise_for_status()
            res_dict = await res.json(encoding="utf-8")

            # data = requests.post(f"{self.BASE_URL}/rest/app/community/platform/getUser", json={},
            #                      verify=False).json()
            # LogUtils.d(data)
            return res_dict

    async def third_login(self, username, password):
        headers = {
            # "Authorization": f"Bearer {accessToken}"
        }
        data = {
            "appTerminalId": self.appTerminalId,
            "password": password,
            "appTerminalModel": self.appTerminalModel,
            "loginMark": "0",
            "osVersion": "12",
            "appTerminalName": "null",
            "osType": "1",
            "packageName": "com.leelen.luxdomo",
            "userName": username,
            "autoLogin": "0"
        }
        # data = requests.post(f"{self.RD_BASE_URL}/rest/api/third/app/user/login", headers=headers, data=data,
        #                      verify=False).json()
        # LogUtils.d(data)
        session = async_get_clientsession(self._hass)

        async with session.post(
                f"{self.RD_BASE_URL}/rest/api/third/app/user/login",
                verify_ssl=False,
                headers=headers,
                data=data,
        ) as res:
            res.raise_for_status()
            res_dict = await res.json(encoding="utf-8")
            return res_dict

    async def VerifyCode(self, username):
        params = GetVerifyCodeRequestParam(username=username)
        # params = encrypt_params(params, publicKey)
        baseRequest = BaseRequest()
        baseRequest.params = params.to_dict()
        baseRequest.seq = 93
        LogUtils.d(json.dumps(baseRequest.to_dict()))
        session = async_get_clientsession(self._hass)
        async with session.post(
                f"{self.BASE_URL}/rest/app/community/security/getVerifyCode",
                verify_ssl=False,
                json=baseRequest.to_dict(),
        ) as res:
            res.raise_for_status()
            data = await res.json(encoding="utf-8")
            LogUtils.d(data)
            self.verifyCodeSign = data.get("params")
            self.username = username
            return data

    async def verifyCodeLogin(self, username=None, verifyCode=None, verifyCodeSign=None, publicKey=None):
        params = CodeLoginRequestParam()
        params.username = username
        params.Phone = username
        params.verifyCode = verifyCode
        params.verifyCodeSign = verifyCodeSign
        params.terminalId = self.appTerminalId
        LogUtils.d(json.dumps(params.to_dict()))

        params = self.encrypt_params(params.to_dict(), publicKey)
        baseRequest = BaseRequest()
        baseRequest.params = params.to_dict()
        baseRequest.seq = 93
        LogUtils.d(json.dumps(baseRequest.to_dict()))

        session = async_get_clientsession(self._hass)

        async with session.post(
                f"{self.BASE_URL}/rest/app/community/user/verifyCodeLogin",
                verify_ssl=False,
                json=baseRequest.to_dict(),
        ) as res:
            res.raise_for_status()
            data = await res.json(encoding="utf-8")
            LogUtils.d(baseRequest.to_dict())
            LogUtils.d(data)
            if data["result"] != 1:
                raise Exception(data["message"])
            self.verifyCodeSign = data.get("params")
            self.username = username
            return data

    async def code_login(self, verifyCode):
        self.uuid = await self.get_uuid()
        code_login_result = await self.verifyCodeLogin(self.username, verifyCode, self.verifyCodeSign, self.uuid)
        accessToken = code_login_result.get("params", {}).get("accessToken")
        user_data = await self.get_user(accessToken)
        username = user_data.get("params", {}).get("userName")
        password = user_data.get("params", {}).get("password")
        data = await self.third_login(username, password)
        bindCallers = data.get("bindCallers")
        accountId = data.get("accountId")
        if len(bindCallers) > 0:
            deviceAddr = bindCallers[0].get("deviceAddr")
            return {
                "username": username,
                "password": password,
                "deviceAddr": deviceAddr,
                "accountId": accountId
            }
        else:
            raise Exception("该账号未绑定网关设备")


    async def get_uuid(self):
        session = async_get_clientsession(self._hass)
        async with session.post(
                f"{self.BASE_URL}/rest/app/community/safe/getUuid",
                verify_ssl=False,
                json={},
        ) as res:
            res.raise_for_status()
            data = await res.json(encoding="utf-8")
            LogUtils.d(data)
            self.uuid = data.get("params", {}).get("uuid")
            return data.get("params", {}).get("uuid")

    def encrypt_params(self, obj: Any, public_key: str) -> 'BaseParam':
        """Encrypt parameters using AES and RSA encryption."""
        json_string = json.dumps(obj).replace(" ", "")
        secret = self.get_secret(16)
        sha256_hash = hashlib.sha256(json_string.encode())
        encrypted_hash = sha256_hash.hexdigest()

        # Create and populate BaseParam
        base_param = BaseParam()
        base_param.data = AesCoder.http_encrypt(json_string, secret)  # Assuming http_encrypt() exists
        base_param.value = RSAEncrypt.rsa_encrypt(secret, public_key)  # Assuming rsa_encrypt() exists
        base_param.hash = encrypted_hash
        return base_param

    async def login(self, username, password, publicKey):
        params = {
            "accountType": 1,
            "appVersion": "5.1.13",
            "intlPhoneCode": 86,
            "osType": 2,
            "osVersion": "12",
            "password": hashlib.sha256(password.encode('utf-8')).hexdigest(),
            "terminalId": self.appTerminalId,
            "terminalModel": self.appTerminalModel,
            "terminalName": self.appTerminalModel,
            "timestamp": int(time.time() * 1000),
            "uniqueCode": str(uuid.uuid4()),
            "username": username
        }

        params = self.encrypt_params(params, publicKey)
        baseRequest = BaseRequest()
        baseRequest.params = params.to_dict()
        baseRequest.seq = 93
        # print(json.dumps(baseRequest.to_dict()))

        session = async_get_clientsession(self._hass)
        async with session.post(
                f"{self.BASE_URL}/rest/app/community/user/encryptV1Login",
                verify_ssl=False,
                json=baseRequest.to_dict(),
        ) as res:
            res.raise_for_status()
            data = await res.json(encoding="utf-8")
            # self.uuid = data.get("params", {}).get("uuid")
            return data

    async def async_download_file(self, device_addr: str, save_path: str = "dump.db") -> bool:
        url = f"{self.BASE_URL}/doc/{device_addr}/1/dump.db"

        """异步下载文件并保存到本地"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    # 检查HTTP状态码
                    if response.status != 200:
                        raise ClientError(
                            f"下载失败，状态码: {response.status}，URL: {url}"
                        )

                    # 异步写入文件
                    async with aiofiles.open(save_path, "wb") as file:
                        async for chunk in response.content.iter_chunked(8192):
                            await file.write(chunk)
                    return True

        except ClientError as e:
            if os.path.exists(save_path):
                LogUtils.w(f"文件下载失败{str(e)}，使用已下载数据")
                return True
            # 处理HTTP/网络错误
            raise Exception(f"网络请求失败: {str(e)}")
        except Exception as e:
            # 处理其他异常（如文件权限错误）
            raise Exception(f"下载异常: {str(e)}")
        return False


    async def refresh_devices(self, device_addr):
        db_path = "./dump.db"
        if await self.async_download_file(device_addr, db_path):
            return await self.query_devices(db_path)

    async def query_devices(self, db_path: str = "dump.db"):
        """使用with自动管理连接"""
        result = []
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row  # ✅ 设置 row_factory 才能用 dict(row)
            cursor = await db.execute("select dev_addr,dev_type,dev_name,sn from dev_tbl;")
            all_devices = await cursor.fetchall()
            for row in all_devices:
                device = dict(row)
                device["logic_srv"] = []
                device["all_property"] = []
                dev_addr, dev_type, dev_name, sn = row
                cursor2 = await db.execute(
                    f"select * from logic_srv_tbl where dev_addr = '{dev_addr}' and logic_type !=0  and srv_type !=0 and display=1 ;")
                all_logic_srv = await cursor2.fetchall()
                for row2 in all_logic_srv:
                    logic_srv = dict(row2)
                    device["logic_srv"].append(logic_srv)

                cursor3 = await db.execute(
                    f"select * from property_tbl where addr = '{dev_addr}' ;")
                all_property = await cursor3.fetchall()
                for row2 in all_property:
                    property = dict(row2)
                    device["all_property"].append(property)

                result.append(device)
        return result

    async def query_gateway_ip(self, db_path: str = "dump.db"):
        """使用with自动管理连接"""
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row  # ✅ 设置 row_factory 才能用 dict(row)
            cursor = await db.execute(
                "select val from dev_tbl  a , property_tbl b where a.dev_addr =b.addr and b.property_id=163;")
            all_ips = await cursor.fetchall()
            LogUtils.d(f"✅ get gateway ip {all_ips}")
            for row in all_ips:
                device = dict(row)
                LogUtils.d(f"gateway ip {device}")
                device["logic_srv"] = []
                return device.get("val")

