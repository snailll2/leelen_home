"""底层协议/工具层测试:VSwitch 状态映射、配置变更通知路径、LAN TLS 上下文构建。

这些模块不依赖 HA,可直接在普通 pytest 下运行(conftest 会把 custom_components 加进路径)。
"""
import binascii
import datetime
import glob
import os
import ssl
import sys
import tempfile
import unittest

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID

# 与 test_pure_logic.py 一致:让 leelen_home.* 可直接导入(容器里为 /config/custom_components)
sys.path.insert(0, os.environ.get("LEELEN_COMPONENTS_PATH", "/config/custom_components"))

from leelen_home.leelen.common.CommonModel import CommonModel  # noqa: E402
from leelen_home.leelen.common.LeelenType import FunctionType  # noqa: E402
from leelen_home.leelen.entity.dao.ConfigDao import ConfigDao  # noqa: E402
from leelen_home.leelen.models.LanDataResponseHandleModel import LanDataResponseHandleModel  # noqa: E402
from leelen_home.leelen.utils.SslUtils import SslUtils  # noqa: E402


def _make_cert(common_name: str, issuer=None, issuer_key=None):
    """生成一张自签或由 issuer 签发的证书,返回 (key, cert)。"""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    issuer_name = issuer.subject if issuer else subject
    signing_key = issuer_key or key
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer_name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=365))
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(signing_key, hashes.SHA256())
    )
    return key, cert


def _p12_hex(key, cert, password: str, extra_certs=None) -> str:
    data = pkcs12.serialize_key_and_certificates(
        name=b"leelen",
        key=key,
        cert=cert,
        cas=extra_certs,
        encryption_algorithm=serialization.BestAvailableEncryption(password.encode()),
    )
    return binascii.hexlify(data).decode()


def _ca_p12_hex(ca_cert, password: str) -> str:
    """只含 CA 证书链的 p12 —— 对应代码里 bks_hex 那个入参(additional_certs 来源)。"""
    data = pkcs12.serialize_key_and_certificates(
        name=b"leelen-ca",
        key=None,
        cert=None,
        cas=[ca_cert],
        encryption_algorithm=serialization.BestAvailableEncryption(password.encode()),
    )
    return binascii.hexlify(data).decode()


class TestVSwitchStateMapping(unittest.TestCase):
    """V设备(布防)上报的状态映射。"""

    def setUp(self):
        # CommonModel 是单例,直接取实例即可(内部逻辑无状态)
        self.model = CommonModel.get_instance()

    def test_arm_payload_maps_to_on(self):
        state = self.model.get_v_switch_state(1, FunctionType.FUNCTION_ARM, bytes([1, 0, 0, 0]))
        self.assertEqual(state.power_state, 1, "\\x01 开头应映射为 1(开)")

    def test_disarm_payload_maps_to_off_not_unknown(self):
        """关必须映射为 2 —— VSwitch 用 power_state in (1,2) 判断上报是否有效。

        映射成 0 会被当作「未携带状态」丢弃,导致 V设备关状态无法从设备上报刷新。
        """
        state = self.model.get_v_switch_state(1, FunctionType.FUNCTION_ARM_CONDITION,
                                              bytes([2, 0, 0, 0]))
        self.assertEqual(state.power_state, 2, "\\x02 开头应映射为 2(关),而不是 0")

    def test_short_or_missing_payload_does_not_raise(self):
        """短包/空包不得抛异常(原实现在日志里无条件索引 state_bytes[0..3])。"""
        for payload in (None, b"", bytes([1]), bytes([1, 0]), bytes([2, 0, 0])):
            state = self.model.get_v_switch_state(1, FunctionType.FUNCTION_ARM, payload)
            self.assertEqual(state.power_state, 0, f"payload={payload!r} 应视为未携带状态")


class TestConfigModifyNotify(unittest.TestCase):
    """协议 771(配置变更通知)路径:曾经因未导入 ConnectLan/ConnectState 必抛 NameError。"""

    def setUp(self):
        LanDataResponseHandleModel.reset_instance()
        self.model = LanDataResponseHandleModel.get_instance()
        self.calls = []
        calls = self.calls

        class _Req:
            """替身:记录模型下发的请求,替代真实的 LanDataRequestModel。"""

            @staticmethod
            def request_config_query():
                calls.append("config_query")

            @staticmethod
            def get_state_data():
                calls.append("state_data")

        self.model.m_lan_data_request_model = _Req()

    def _protocol(self, body: dict):
        class _P:
            request_data_body = __import__("json").dumps(body)
        return _P()

    def test_notify_without_connection_only_logs(self):
        """链路未就绪时不抛异常,也不下发会被丢弃的请求帧。"""
        # 确保没有活跃连接
        from leelen_home.leelen.HeartbeatService import HeartbeatService
        HeartbeatService.get_instance().connect_lan = None

        # 让版本比较走「不相等」分支(ConfigDao.config_version 恒为 0)
        ConfigDao.get_instance().config.config_version = 0
        self.model.handle_config_modify_notify(
            self._protocol({"config_version": 12345, "T2": 999})
        )
        self.assertEqual(self.calls, [], "未登录时不应下发请求")

    def test_notify_with_active_connection_queries_config(self):
        """已连接且已登录时,应查询配置并拉一次状态(替代 Java 的 downloadGatewayDb)。"""
        from leelen_home.leelen.BaseConnect import ConnectState, LogonState
        from leelen_home.leelen.HeartbeatService import HeartbeatService

        class _Conn:
            @staticmethod
            def get_connect_state():
                return ConnectState.CONNECTED

            @staticmethod
            def get_logon_state():
                return LogonState.LOGGED_ON

        HeartbeatService.get_instance().connect_lan = _Conn()
        ConfigDao.get_instance().config.config_version = 0

        self.model.handle_config_modify_notify(
            self._protocol({"config_version": 12345, "T2": 999})
        )
        self.assertEqual(self.calls, ["config_query", "state_data"])

    def test_notify_matching_version_and_newer_time_queries_then_returns(self):
        """版本相同且云端时间更新:只查配置,不再拉状态(Java 的快路径)。"""
        from leelen_home.leelen.HeartbeatService import HeartbeatService
        HeartbeatService.get_instance().connect_lan = None

        ConfigDao.get_instance().config.config_version = 777
        ConfigDao.get_instance().config.latest_time = 100
        self.model.handle_config_modify_notify(
            self._protocol({"config_version": 777, "T2": 200})
        )
        self.assertEqual(self.calls, ["config_query"])

    def test_malformed_body_is_swallowed(self):
        """坏报文不应抛出(收包线程里异常会打断分发链)。"""
        class _P:
            request_data_body = b"{not json"
        self.model.handle_config_modify_notify(_P())


class TestSslUtils(unittest.TestCase):
    """LAN TLS 上下文:构建成功且不残留私钥临时文件。"""

    def test_context_built_and_temp_files_cleaned(self):
        ca_key, ca_cert = _make_cert("leelen-ca")
        client_key, client_cert = _make_cert("leelen-client", ca_cert, ca_key)
        p12_hex = _p12_hex(client_key, client_cert, "pw123")
        ca_p12_hex = _ca_p12_hex(ca_cert, "pw123")

        before = set(glob.glob(os.path.join(tempfile.gettempdir(), "tmp*")))
        context = SslUtils.get_lan_socket_ssl_context(p12_hex, "pw123", ca_p12_hex, "pw123")
        after = set(glob.glob(os.path.join(tempfile.gettempdir(), "tmp*")))

        self.assertIsInstance(context, ssl.SSLContext)
        # 双向 TLS:要求对端出示证书,但不按主机名校验(网关证书 CN 不是 LAN IP)
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertFalse(context.check_hostname)
        # 版本与密码套件必须钉死在与网关一致的组合上(TLS1.2 + AES256-GCM-SHA384)
        self.assertEqual(context.minimum_version, ssl.TLSVersion.TLSv1_2)
        self.assertEqual(context.maximum_version, ssl.TLSVersion.TLSv1_2)
        # set_ciphers 只作用于 ≤TLS1.2 的套件(TLS1.3 套件由 max_version 排除)
        ciphers_12 = [c["name"] for c in context.get_ciphers() if c["protocol"] != "TLSv1.3"]
        self.assertEqual(ciphers_12, ["AES256-GCM-SHA384"])
        # 私钥/证书临时文件必须已删除:原实现 delete=False 且从不清理
        leaked = after - before
        self.assertEqual(leaked, set(), f"不应残留临时文件(含私钥): {leaked}")

    def test_missing_ca_chain_raises_and_cleans_up(self):
        client_key, client_cert = _make_cert("leelen-client")
        p12_hex = _p12_hex(client_key, client_cert, "pw123")
        # 没有 CA 的 p12 → additional_certs 为空 → 应抛错
        before = set(glob.glob(os.path.join(tempfile.gettempdir(), "tmp*")))
        with self.assertRaises(ValueError):
            SslUtils.get_lan_socket_ssl_context(p12_hex, "pw123", p12_hex, "pw123")
        after = set(glob.glob(os.path.join(tempfile.gettempdir(), "tmp*")))
        self.assertEqual(after - before, set(), "异常路径同样不应残留临时文件")


class TestSingletonLockNotShared(unittest.TestCase):
    """单例锁不可跨类共享 —— 否则构造期取另一个单例会永久自死锁。"""

    def test_each_singleton_has_its_own_lock(self):
        from leelen_home.leelen.common.SingletonMixin import SingletonMixin

        class _A(SingletonMixin):
            pass

        class _B(SingletonMixin):
            pass

        self.assertIsNot(_A._singleton_lock, _B._singleton_lock,
                         "不同单例必须各持一把锁")

    def test_nested_singleton_construction_does_not_deadlock(self):
        """LanDataResponseHandleModel.__init__ 会取 LanDataRequestModel 单例。

        共享锁时代这里会自死锁:同一把非重入锁在持锁状态下被二次加锁。
        本用例若挂起即回归(测试超时即失败)。
        """
        LanDataResponseHandleModel.reset_instance()
        # 让被依赖的单例也回到未创建状态,确保构造路径真正走一遍加锁逻辑
        from leelen_home.leelen.models.LanDataRequestModel import LanDataRequestModel
        LanDataRequestModel.reset_instance()

        model = LanDataResponseHandleModel.get_instance()
        self.assertIsNotNone(model)
        self.assertIsNotNone(model.m_lan_data_request_model)


if __name__ == "__main__":
    unittest.main()
