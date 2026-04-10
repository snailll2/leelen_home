"""
广域网连接模块

处理与Leelen云服务器的连接，包括：
- WAN协议处理
- 登录认证
- 心跳维护
- 数据透传

Classes:
    ConnectWan: 广域网连接管理器
"""

import socket
import threading
from typing import Optional, Dict, Callable

from .BaseConnect import BaseConnect, ConnectState, LogonState, ConnectionConfig
from .ConnectLan import ConnectLan
from .common import WanProtocolCmd, DeviceType, ProtocolDefault
from .common.LeelenConst import LeelenConst
from .entity.GatewayInfo import GatewayInfo
from .entity.User import User
from .models.WanDataHandleModel import WanDataHandleModel
from .protocols.BaseWanProtocol import BaseWanProtocol
from .protocols.HeartWanProtocol import HeartWanProtocol
from .protocols.LoginWanProtocol import LoginWanProtocol
from .protocols.PassThroughWanProtocol import PassThroughWanProtocol
from .utils.ConvertUtils import ConvertUtils
from .utils.DataPkgUtils import DataPkgUtils
from .utils.LogUtils import LogUtils
from .utils.Singleton import SingletonBase
from .utils.Exceptions import safe_execute, ProtocolException


class ConnectWan(SingletonBase, BaseConnect):
    """
    广域网连接管理器（单例）

    管理与Leelen云服务器的连接，处理WAN协议通信。

    Attributes:
        MSG_TYPE_LOGON_TIMEOUT: 登录超时消息类型
        SOURCE_DEST_LENGTH: 源/目的地址长度

    Example:
        wan = ConnectWan.get_instance()
        wan.connect()
    """

    # 常量定义
    MSG_TYPE_LOGON_TIMEOUT = 3
    SOURCE_DEST_LENGTH = 8

    # 响应码映射
    _RESPONSE_MESSAGES: Dict[int, str] = {
        1: "succeed.",
        2: "failed.",
        3: "not support.",
        4: "insufficient memory.",
        5: "transfer terminated.",
        6: "username or password wrong.",
        7: "relogon.",
        -124: "logon wrong"
    }

    def __init__(self):
        """初始化WAN连接（使用单例模式，实际初始化只执行一次）"""
        # 注意：SingletonBase会处理单例逻辑
        # 这里不需要调用 super().__init__()，因为 _init_instance 会被调用
        pass

    def _init_instance(self) -> None:
        """
        初始化实例（SingletonBase回调）

        设置服务器地址和初始化状态。
        """
        # 初始化基类
        server_host = "rd.iot.leelen.com"
        BaseConnect.__init__(
            self,
            server_host=server_host,
            server_port=17733,
            username=None,
            password=None,
            config=ConnectionConfig(
                max_connecting_count=5,
                heartbeat_interval=5.0,
                heartbeat_timeout=30.0
            )
        )

        # WAN特有属性
        self._tag = "ConnectWan"
        self._is_get_request_server_id = False

        LogUtils.i(self._tag, "ConnectWan initialized")

    @classmethod
    def get_instance(cls) -> 'ConnectWan':
        """
        获取WAN连接实例

        Returns:
            ConnectWan单例实例
        """
        if cls._instance is None:
            cls()
        return cls._instance

    # region 协议处理

    def handle_protocol_data(self, protocol: BaseWanProtocol) -> None:
        """
        处理WAN协议数据

        根据协议命令类型分发到对应的处理逻辑。

        Args:
            protocol: WAN协议对象
        """
        if not protocol:
            LogUtils.e(self._tag, "No protocol to handle")
            return

        # 更新心跳时间
        self.recv_heartbeat()

        # 命令分发
        cmd_handlers = {
            WanProtocolCmd.APP_LOGON: self._handle_login_response,
            WanProtocolCmd.HEARTBEAT: self._handle_heartbeat_response,
            WanProtocolCmd.PUSH_MSG: self._handle_push_message,
            WanProtocolCmd.REPEAT_LOGIN: self._handle_repeat_login,
            WanProtocolCmd.PASS_THROUGH: self._handle_pass_through,
            WanProtocolCmd.LOGOUT_GATEWAY: self._handle_logout_gateway,
            WanProtocolCmd.GATEWAY_ONLINE: self._handle_gateway_online,
            WanProtocolCmd.GET_GATEWAY_SERVER: self._handle_get_gateway_server,
            WanProtocolCmd.GATEWAY_REPLACE_STATE: self._handle_gateway_replace_state,
        }

        handler = cmd_handlers.get(protocol.cmd)
        if handler:
            handler(protocol)
        else:
            LogUtils.w(self._tag, f"Unknown command: {protocol.cmd.hex()}")

    def _handle_login_response(self, protocol: BaseWanProtocol) -> None:
        """
        处理登录响应

        Args:
            protocol: 协议对象
        """
        response_code = protocol.response_code

        # 判断登录结果
        if response_code == 1:
            success = True
            self._heartbeat_data = self.create_heartbeat_data()
            message = self._RESPONSE_MESSAGES.get(1, "succeed.")
        elif response_code == 7:
            success = True
            message = self._RESPONSE_MESSAGES.get(7, "relogon.")
        else:
            success = False
            message = self._RESPONSE_MESSAGES.get(
                response_code,
                f"unknown error (code: {response_code})"
            )

            # 特殊错误处理
            if response_code == 6 and User.get_instance().is_login():
                WanDataHandleModel.get_instance().response_password_changed()

        LogUtils.i(
            self._tag,
            f"WAN login result: success={success}, code={response_code}, msg={message}"
        )

        # 更新登录状态
        self.logon_state = (
            LogonState.LOGGED_ON if success else LogonState.NONE
        )

        # 登录成功后获取设备列表和服务器ID
        if success:
            gateway_info = GatewayInfo.get_instance()
            if gateway_info.get_gateway_desc() != gateway_info.default_desc:
                LogUtils.d(self._tag, "Login success, requesting server ID")
                WanDataHandleModel.get_instance().request_wan_server_id()

    def _handle_heartbeat_response(self, protocol: BaseWanProtocol) -> None:
        """
        处理心跳响应

        Args:
            protocol: 协议对象
        """
        success = protocol.response_code == 1
        LogUtils.i(self._tag, f"WAN heartbeat response: {success}")

    def _handle_push_message(self, protocol: BaseWanProtocol) -> None:
        """
        处理推送消息

        Args:
            protocol: 协议对象
        """
        LogUtils.i(self._tag, "Received push message")
        # TODO: 实现推送消息处理
        # src = ConvertUtils.get_long_address_by_type(
        #     DeviceType.APP,
        #     User.get_instance().get_account_id()
        # )
        # dest = ConvertUtils.get_long_address_by_type(DeviceType.SERVER, 0)

    def _handle_repeat_login(self, protocol: BaseWanProtocol) -> None:
        """
        处理重复登录通知

        Args:
            protocol: 协议对象
        """
        if protocol.request_data_body and len(protocol.request_data_body) > 0:
            if protocol.request_data_body[0] == 0:
                LogUtils.i(self._tag, "User logged in elsewhere")
            else:
                LogUtils.i(self._tag, "User password changed")
                WanDataHandleModel.get_instance().response_password_changed()

    def _handle_pass_through(self, protocol: BaseWanProtocol) -> None:
        """
        处理透传数据

        Args:
            protocol: 协议对象
        """
        LogUtils.d(self._tag, "WAN pass-through data received")

        if protocol.request_data and not ConnectLan.get_instance().is_logged_on():
            PassThroughWanProtocol.get_instance().handle_pass_through_callback(
                protocol.request_data
            )
        else:
            LogUtils.i(self._tag, "Request data is null or LAN is connected")

    def _handle_logout_gateway(self, protocol: BaseWanProtocol) -> None:
        """
        处理网关登出

        Args:
            protocol: 协议对象
        """
        LogUtils.d(self._tag, "WAN clear server ID")
        GatewayInfo.get_instance().set_wan_server_code(None)

    def _handle_gateway_online(self, protocol: BaseWanProtocol) -> None:
        """
        处理网关上线通知

        Args:
            protocol: 协议对象
        """
        LogUtils.d(self._tag, "Gateway online, re-requesting server ID")
        WanDataHandleModel.get_instance().request_wan_server_id()

    def _handle_get_gateway_server(self, protocol: BaseWanProtocol) -> None:
        """
        处理获取网关服务器响应

        Args:
            protocol: 协议对象
        """
        LogUtils.d(self._tag, "WAN get server ID response")
        WanDataHandleModel.get_instance().response_wan_server_id(protocol)

    def _handle_gateway_replace_state(self, protocol: BaseWanProtocol) -> None:
        """
        处理网关替换状态

        Args:
            protocol: 协议对象
        """
        if protocol.request_data_body and len(protocol.request_data_body) > 0:
            state = protocol.request_data_body[0]
            LogUtils.d(self._tag, f"WAN gateway replace state: {state}")
            # TODO: 实现网关替换状态处理

    # endregion

    # region 数据接收处理

    def handle_recv_data(self, data: bytes) -> None:
        """
        处理接收到的原始数据

        解析数据包并分发到协议处理器。

        Args:
            data: 接收到的原始数据
        """
        if not data:
            LogUtils.e(self._tag, "Received null data")
            return

        # 检查数据长度
        if len(data) > 0 and len(data) == (data[0] & 0xFF):
            # 单包数据
            protocol = BaseWanProtocol.parse(data)
            if protocol:
                self.handle_protocol_data(protocol)
        else:
            # 多包数据，使用DataPkgUtils处理
            DataPkgUtils.push_wan(data)
            protocols = DataPkgUtils.pull_wan()

            if protocols:
                for protocol in protocols:
                    self.handle_protocol_data(protocol)
            else:
                LogUtils.i(self._tag, "No complete packets available")

    # endregion

    # region 数据发送

    def add_request(self, data: bytes) -> None:
        """
        添加请求数据

        将LAN数据通过WAN通道发送。

        Args:
            data: 要发送的LAN数据
        """
        with threading.Lock():
            # 获取源地址
            src = ConvertUtils.get_long_address_by_type(
                DeviceType.APP,
                User.get_instance().get_account_id()
            )
            dest = GatewayInfo.get_instance().get_gateway_desc()

            # 验证源地址
            if len(src) != self.SOURCE_DEST_LENGTH:
                LogUtils.w(self._tag, "Invalid source address")
                return

            # 检查服务器ID
            server_code = GatewayInfo.get_instance().get_wan_server_code()
            default_id = ProtocolDefault.DEFAULT_WAN_SERVER_ID

            try:
                if server_code == default_id:
                    LogUtils.d(self._tag, "Requesting WAN server ID")
                    self._is_get_request_server_id = True
                    WanDataHandleModel.get_instance().request_wan_server_id()
                    return
            except Exception as e:
                LogUtils.e(self._tag, f"Server ID check error: {e}")
                return

            # 验证目的地址并发送
            if dest and len(dest) == self.SOURCE_DEST_LENGTH:
                protocol = PassThroughWanProtocol.get_instance()
                protocol.set_lan_data(data)
                protocol.set_src_dest(src, dest)
                self.send_data(protocol.get_request_data())
            else:
                LogUtils.w(self._tag, "Invalid destination address")

    # endregion

    # region 心跳和登录

    def create_heartbeat_data(self) -> bytes:
        """
        创建心跳数据

        Returns:
            心跳数据字节串
        """
        src = ConvertUtils.get_long_address_by_type(
            DeviceType.APP,
            User.get_instance().get_account_id()
        )
        dest = ConvertUtils.get_long_address_by_type(DeviceType.SERVER, 0)
        return HeartWanProtocol.get_instance().get_request_data(src, dest)

    def send_logon_data(self) -> None:
        """发送登录数据"""
        LogUtils.i(self._tag, "Sending login data")

        user = User.get_instance()
        if user.is_project_account():
            LogUtils.d(self._tag, "Project account, skip WAN login")
            return

        # 构建登录协议
        protocol = LoginWanProtocol.get_instance()
        protocol.set_app_user(user.get_username())
        protocol.set_app_pwd(user.get_password())
        protocol.set_logon_mark(0)

        src = ConvertUtils.get_long_address_by_type(
            DeviceType.APP,
            user.get_account_id()
        )
        dest = GatewayInfo.get_instance().get_gateway_desc()
        data = protocol.get_request_data(src, dest)

        # 发送登录请求
        self.logon_state = LogonState.LOGGING_ON
        self.send_data(data)

    # endregion

    # region 回调方法

    def on_connect_result(self, success: bool) -> None:
        """
        连接结果回调

        Args:
            success: 是否连接成功
        """
        if success and self._socket:
            try:
                self._socket.settimeout(0)
            except socket.error as e:
                LogUtils.e(self._tag, f"Set socket timeout error: {e}")
            self.logon()
        else:
            self.connect()

    def on_server_host_empty(self) -> None:
        """服务器地址为空时的回调"""
        LogUtils.i(self._tag, "Server host is empty")

    # endregion

    # region 公共方法

    def reset_wan(self) -> None:
        """重置WAN连接"""
        self.reset()

    def set_get_request_server_id(self, value: bool = False) -> None:
        """
        设置请求服务器ID标志

        Args:
            value: 标志值
        """
        self._is_get_request_server_id = value

    # endregion
