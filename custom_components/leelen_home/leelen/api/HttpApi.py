"""HTTP API client for Leelen Cloud."""
import hashlib
import json
import os
import random
import string
import threading
import time
import uuid
from typing import Any

import aiofiles
import aiohttp
import aiosqlite
from aiohttp import ClientError
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from ..entity.BaseParam import BaseParam, CodeLoginRequestParam, GetVerifyCodeRequestParam
from ..entity.BaseRequest import BaseRequest
from ..utils.AesCoder import AesCoder
from ..utils.LogUtils import LogUtils
from ..utils.RSAEncrypt import RSAEncrypt


class HttpApi:
    """Leelen HTTP API client (Singleton)."""

    _instance: "HttpApi" = None
    _lock = threading.Lock()

    BASE_URL = "https://iot.leelen.com"
    RD_BASE_URL = "https://rd.iot.leelen.com"

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass
        self.device_addr = ""
        self.appTerminalId = f"ANDROID-{self._generate_terminal_id()}"
        self.appTerminalModel = "REP-AN00"
        self.uuid: str | None = None
        self.verifyCodeSign = ""
        self.username = ""
        self._device_list: list[dict] = []

    @staticmethod
    def _generate_secret(length: int) -> str:
        """Generate random secret string."""
        chars = string.ascii_letters + string.digits
        return ''.join(random.choice(chars) for _ in range(length))

    @staticmethod
    def _generate_terminal_id() -> str:
        """Generate terminal ID."""
        random_str = ''.join(random.choices(string.ascii_letters + string.digits, k=32))
        return hashlib.md5(random_str.encode()).hexdigest()

    @classmethod
    def get_instance(cls, hass: HomeAssistant = None) -> "HttpApi":
        """Get singleton instance."""
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = HttpApi(hass)
        return cls._instance

    async def get_user(self, access_token: str) -> dict:
        """Get user info by access token."""
        session = async_get_clientsession(self._hass)
        headers = {"Authorization": f"Bearer {access_token}"}
        async with session.post(
            f"{self.BASE_URL}/rest/app/community/platform/getUser",
            verify_ssl=False,
            headers=headers,
            json={},
        ) as res:
            res.raise_for_status()
            return await res.json(encoding="utf-8")

    async def third_login(self, username: str, password: str) -> dict:
        """Third-party login."""
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
        session = async_get_clientsession(self._hass)
        async with session.post(
            f"{self.RD_BASE_URL}/rest/api/third/app/user/login",
            verify_ssl=False,
            data=data,
        ) as res:
            res.raise_for_status()
            return await res.json(encoding="utf-8")

    async def VerifyCode(self, username: str) -> dict:
        """Request verification code."""
        params = GetVerifyCodeRequestParam(username=username)
        base_request = BaseRequest()
        base_request.params = params.to_dict()
        base_request.seq = 93
        LogUtils.d(__name__, json.dumps(base_request.to_dict()))

        session = async_get_clientsession(self._hass)
        async with session.post(
            f"{self.BASE_URL}/rest/app/community/security/getVerifyCode",
            verify_ssl=False,
            json=base_request.to_dict(),
        ) as res:
            res.raise_for_status()
            data = await res.json(encoding="utf-8")
            LogUtils.d(__name__, str(data))
            self.verifyCodeSign = data.get("params")
            self.username = username
            return data

    async def verifyCodeLogin(
        self,
        username: str | None = None,
        verify_code: str | None = None,
        verify_code_sign: str | None = None,
        public_key: str | None = None,
    ) -> dict:
        """Login with verification code."""
        params = CodeLoginRequestParam()
        params.username = username
        params.Phone = username
        params.verifyCode = verify_code
        params.verifyCodeSign = verify_code_sign
        params.terminalId = self.appTerminalId
        LogUtils.d(__name__, json.dumps(params.to_dict()))

        encrypted_params = self._encrypt_params(params.to_dict(), public_key)
        base_request = BaseRequest()
        base_request.params = encrypted_params.to_dict()
        base_request.seq = 93
        LogUtils.d(__name__, json.dumps(base_request.to_dict()))

        session = async_get_clientsession(self._hass)
        async with session.post(
            f"{self.BASE_URL}/rest/app/community/user/verifyCodeLogin",
            verify_ssl=False,
            json=base_request.to_dict(),
        ) as res:
            res.raise_for_status()
            data = await res.json(encoding="utf-8")
            LogUtils.d(__name__, str(base_request.to_dict()))
            LogUtils.d(__name__, str(data))
            if data.get("result") != 1:
                raise Exception(data.get("message", "Unknown error"))
            self.verifyCodeSign = data.get("params")
            self.username = username
            return data

    async def code_login(self, verify_code: str) -> dict:
        """Complete login flow with verification code."""
        self.uuid = await self._get_uuid()
        login_result = await self.verifyCodeLogin(
            self.username, verify_code, self.verifyCodeSign, self.uuid
        )
        access_token = login_result.get("params", {}).get("accessToken")
        user_data = await self.get_user(access_token)
        username = user_data.get("params", {}).get("userName")
        password = user_data.get("params", {}).get("password")

        data = await self.third_login(username, password)
        bind_callers = data.get("bindCallers", [])
        account_id = data.get("accountId")

        if not bind_callers:
            raise Exception("该账号未绑定网关设备")

        return {
            "username": username,
            "password": password,
            "deviceAddr": bind_callers[0].get("deviceAddr"),
            "accountId": account_id,
        }


    async def _get_uuid(self) -> str | None:
        """Get UUID from server."""
        session = async_get_clientsession(self._hass)
        async with session.post(
            f"{self.BASE_URL}/rest/app/community/safe/getUuid",
            verify_ssl=False,
            json={},
        ) as res:
            res.raise_for_status()
            data = await res.json(encoding="utf-8")
            LogUtils.d(__name__, str(data))
            self.uuid = data.get("params", {}).get("uuid")
            return self.uuid

    def _encrypt_params(self, obj: Any, public_key: str) -> 'BaseParam':
        """Encrypt parameters using AES and RSA encryption."""
        json_string = json.dumps(obj).replace(" ", "")
        secret = self._generate_secret(16)
        encrypted_hash = hashlib.sha256(json_string.encode()).hexdigest()

        base_param = BaseParam()
        base_param.data = AesCoder.http_encrypt(json_string, secret)
        base_param.value = RSAEncrypt.rsa_encrypt(secret, public_key)
        base_param.hash = encrypted_hash
        return base_param

    async def login(self, username: str, password: str, public_key: str) -> dict:
        """Login with username and password."""
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

        encrypted_params = self._encrypt_params(params, public_key)
        base_request = BaseRequest()
        base_request.params = encrypted_params.to_dict()
        base_request.seq = 93

        session = async_get_clientsession(self._hass)
        async with session.post(
            f"{self.BASE_URL}/rest/app/community/user/encryptV1Login",
            verify_ssl=False,
            json=base_request.to_dict(),
        ) as res:
            res.raise_for_status()
            return await res.json(encoding="utf-8")

    async def async_download_file(self, device_addr: str, save_path: str = "dump.db") -> bool:
        """Download device database file."""
        url = f"{self.BASE_URL}/doc/{device_addr}/1/dump.db"
        """异步下载文件并保存到本地"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        raise ClientError(f"下载失败，状态码: {response.status}，URL: {url}")

                    async with aiofiles.open(save_path, "wb") as file:
                        async for chunk in response.content.iter_chunked(8192):
                            await file.write(chunk)
                    return True

        except ClientError as exc:
            if os.path.exists(save_path):
                LogUtils.w(__name__, f"文件下载失败{exc}，使用已下载数据")
                return True
            raise Exception(f"网络请求失败: {exc}") from exc
        except Exception as exc:
            raise Exception(f"下载异常: {exc}") from exc


    async def refresh_devices(self, device_addr: str) -> list[dict]:
        """Refresh devices from cloud."""
        db_path = "./dump.db"
        if await self.async_download_file(device_addr, db_path):
            return await self.query_devices(db_path)
        return []

    async def query_devices(self, db_path: str = "dump.db") -> list[dict]:
        """Query devices from local database."""
        result = []
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT dev_addr, dev_type, dev_name, sn FROM dev_tbl;"
            )
            all_devices = await cursor.fetchall()

            for row in all_devices:
                device = dict(row)
                dev_addr = device["dev_addr"]
                device["logic_srv"] = []
                device["all_property"] = []

                # Query logic services
                cursor2 = await db.execute(
                    """SELECT * FROM logic_srv_tbl
                       WHERE dev_addr = ? AND logic_type != 0
                       AND srv_type != 0 AND display = 1""",
                    (dev_addr,)
                )
                device["logic_srv"] = [dict(r) for r in await cursor2.fetchall()]

                # Query properties
                cursor3 = await db.execute(
                    "SELECT * FROM property_tbl WHERE addr = ?",
                    (dev_addr,)
                )
                device["all_property"] = [dict(r) for r in await cursor3.fetchall()]

                result.append(device)
        return result

    async def query_gateway_ip(self, db_path: str = "dump.db") -> str | None:
        """Query gateway IP from database."""
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """SELECT val FROM dev_tbl a
                   JOIN property_tbl b ON a.dev_addr = b.addr
                   WHERE b.property_id = 163"""
            )
            row = await cursor.fetchone()
            if row:
                ip = dict(row).get("val")
                LogUtils.d(__name__, f"Gateway IP: {ip}")
                return ip
        return None

