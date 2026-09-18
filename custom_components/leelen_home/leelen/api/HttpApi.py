import os
import hashlib
import json
import random
import string
import time
import uuid
from typing import Any

import aiofiles as aiofiles
import aiosqlite
from aiohttp import ClientError
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from ..common.SingletonMixin import SingletonMixin
from ..entity.BaseParam import BaseParam, CodeLoginRequestParam, GetVerifyCodeRequestParam
from ..entity.BaseRequest import BaseRequest
# from ..process import get_secret
from ..utils.AesCoder import AesCoder
from ..utils.LogUtils import LogUtils
from ..utils.RSAEncrypt import RSAEncrypt

#: 云端下发的设备库文件名,始终解析为 HA 配置目录下的绝对路径。
DUMP_DB_FILENAME = "dump.db"


class HttpApi(SingletonMixin):
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


    def get_terminal_id(self):
        return hashlib.md5(''.join(random.choices(string.ascii_letters + string.digits, k=32)).encode()).hexdigest()

    async def get_user(self, accessToken):
        session = async_get_clientsession(self._hass)
        headers = {
            "Authorization": f"Bearer {accessToken}"
        }
        async with session.post(
                f"{self.BASE_URL}/rest/app/community/platform/getUser",
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
                json=baseRequest.to_dict(),
        ) as res:
            res.raise_for_status()
            data = await res.json(encoding="utf-8")
            LogUtils.d(baseRequest.to_dict())
            LogUtils.d(data)
            if data.get("result") != 1:
                raise Exception(data.get("message", "verifyCodeLogin failed"))
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
        bindCallers = data.get("bindCallers") or []
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
                json=baseRequest.to_dict(),
        ) as res:
            res.raise_for_status()
            data = await res.json(encoding="utf-8")
            # self.uuid = data.get("params", {}).get("uuid")
            return data

    async def async_download_file(self, device_addr: str, save_path: str) -> bool:
        url = f"{self.BASE_URL}/doc/{device_addr}/1/dump.db"

        """异步下载文件并保存到本地(先写临时文件再原子替换,避免覆盖正被读取的库)"""
        tmp_path = save_path + ".tmp"
        try:
            session = async_get_clientsession(self._hass)
            async with session.get(url) as response:
                # 检查HTTP状态码
                if response.status != 200:
                    raise ClientError(
                        f"下载失败，状态码: {response.status}，URL: {url}"
                    )

                # 异步写入文件
                async with aiofiles.open(tmp_path, "wb") as file:
                    async for chunk in response.content.iter_chunked(8192):
                        await file.write(chunk)
            os.replace(tmp_path, save_path)
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
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)


    async def refresh_devices(self, device_addr):
        # db 必须落在 HA 配置目录,不能依赖进程 CWD(容器/服务方式启动时两者不同)。
        db_path = self._hass.config.path(DUMP_DB_FILENAME)
        if await self.async_download_file(device_addr, db_path):
            return await self.query_devices(db_path)

    async def query_devices(self, db_path: str | None = None):
        """读取设备库:每个设备带 logic_srv(仅 logic_type/srv_type 均非 0)与全部 property。

        原先按设备逐条查 logic_srv_tbl / property_tbl(1+2N 次 SQL),现改为对两张表各查一次
        再在内存里按 dev_addr 归组(固定 3 条 SQL)。

        ORDER BY 是为了复现原实现的子表顺序(不是随便加的):
        - property_tbl 原先每个设备内按 property_id 递增(查询走了主键索引);
        - logic_srv_tbl 原先按插入顺序(rowid)。
        logic_srv 的顺序会影响各平台建实体的先后,进而影响 HA 的 entity_id 分配,
        故必须保持一致;property 顺序则仅为稳妥起见一并保持。
        """
        db_path = db_path or self._hass.config.path(DUMP_DB_FILENAME)
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row  # ✅ 设置 row_factory 才能用 dict(row)

            cursor = await db.execute("select dev_addr,dev_type,dev_name,sn from dev_tbl;")
            devices = [dict(row) for row in await cursor.fetchall()]
            for device in devices:
                device["logic_srv"] = []
                device["all_property"] = []
            by_addr = {device["dev_addr"]: device for device in devices}

            cursor = await db.execute(
                "select * from logic_srv_tbl where logic_type != 0 and srv_type != 0 "
                "order by dev_addr, rowid;"
            )
            for row in await cursor.fetchall():
                # 子表里可能有 dev_tbl 已经不存在的遗留行(设备被删),按存在性挂载即可。
                device = by_addr.get(row["dev_addr"])
                if device is not None:
                    device["logic_srv"].append(dict(row))

            cursor = await db.execute("select * from property_tbl order by addr, property_id;")
            for row in await cursor.fetchall():
                device = by_addr.get(row["addr"])
                if device is not None:
                    device["all_property"].append(dict(row))

        return devices

    async def query_gateway_ip(self, db_path: str | None = None):
        """使用with自动管理连接"""
        db_path = db_path or self._hass.config.path(DUMP_DB_FILENAME)
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row  # ✅ 设置 row_factory 才能用 dict(row)
            cursor = await db.execute(
            "select val from dev_tbl  a , property_tbl b where a.dev_addr =b.addr and b.property_id=163 and a.dev_type = 776;")
            all_ips = await cursor.fetchall()
            LogUtils.d(f"✅ get gateway ip {all_ips}")
            for row in all_ips:
                device = dict(row)
                LogUtils.d(f"gateway ip {device}")
                device["logic_srv"] = []
                return device.get("val")

    async def query_rooms(self, db_path: str | None = None):
        """查询房间表(含 room_id == 0 的「客厅」,与其他房间同等对待)。"""
        db_path = db_path or self._hass.config.path(DUMP_DB_FILENAME)
        async with aiosqlite.connect(db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "select room_id, room_name, floor_id from room_tbl order by room_id;")
            all_rooms = await cursor.fetchall()
            return [dict(row) for row in all_rooms]

