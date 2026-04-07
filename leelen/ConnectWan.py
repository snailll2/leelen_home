import socket
import threading

from .BaseConnect import BaseConnect, LogonState
from .ConnectLan import ConnectLan
from .common import WanProtocolCmd, DeviceType, ProtocolDefault
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


class ConnectWan(BaseConnect):
    MSG_TYPE_LOGON_TIMEOUT = 3
    SOURCE_DEST_LENGTH = 8
    _instance = None
    _lock = threading.Lock()

    def __init__(self, host: str):
        super().__init__(host, 17733, None, None)
        self.tag = "ConnectWan"
        self.m_is_get_request_server_id = False
        LogUtils.i("ConnectWan", "ConnectWan constructor")

    @classmethod
    def get_instance(cls) -> 'ConnectWan':
        with cls._lock:
            if not cls._instance:
                # TODO: Get actual server host
                server_host = "rd.iot.leelen.com"
                cls._instance = ConnectWan(server_host)
            return cls._instance

    def handle_protocol_data(self, protocol: BaseWanProtocol) -> None:
        LogUtils.i(self.tag, "handleProtocolData Wan")
        if not protocol:
            LogUtils.e(self.tag, "no protocol to handle.")
            return

        self.recv_heartbeat()

        if protocol.cmd == WanProtocolCmd.APP_LOGON:
            success = True
            msg = ""

            if protocol.response_code == 1:
                self.heartbeat_data = self.create_heartbeat_data()
                msg = "succeed."
            elif protocol.response_code == 7:
                msg = "relogon."
            else:
                success = False
                if protocol.response_code == 6:
                    if User.get_instance().is_login():
                        WanDataHandleModel.get_instance().response_password_changed()
                    msg = "username or password wrong."
                elif protocol.response_code == -124:
                    msg = "logon wrong"
                else:
                    msg = {
                        2: "failed.",
                        3: "not support.",
                        4: "insufficient memory.",
                        5: "transfer terminated."
                    }.get(protocol.response_code, "")

            LogUtils.i(self.tag, f"wan log on return {success} code = {protocol.response_code}, {msg}")

            self.set_logon_state(LogonState.LOGGED_ON if success else LogonState.NONE)

            if success and GatewayInfo.get_instance().get_gateway_desc() != GatewayInfo.get_instance().default_desc:
                LogUtils.d(self.tag, "logon wan success, get device list and server id")
                WanDataHandleModel.get_instance().request_wan_server_id()

        elif protocol.cmd == WanProtocolCmd.HEARTBEAT:
            success = protocol.response_code == 1
            LogUtils.i(self.tag, f"wan heartbeat return {success}")

        elif protocol.cmd == WanProtocolCmd.PUSH_MSG:
            LogUtils.i(self.tag, "push message")
            src = ConvertUtils.get_long_address_by_type(DeviceType.APP, User.get_instance().get_account_id())
            dest = ConvertUtils.get_long_address_by_type(DeviceType.SERVER, 0)
            #
            # push_protocol = PushMsgWanProtocol.get_instance()
            # push_protocol.set_session_id(protocol.session_id)
            # self.send_data(push_protocol.get_response_data(src, dest))

        elif protocol.cmd == WanProtocolCmd.REPEAT_LOGIN:
            if protocol.request_data_body[0] == 0:
                LogUtils.i(self.tag, "user login somewhere")
            else:
                LogUtils.i(self.tag, "user password changed")
                WanDataHandleModel.get_instance().response_password_changed()

        elif protocol.cmd == WanProtocolCmd.PASS_THROUGH:
            LogUtils.d(self.tag, "wan pass through data.")
            if protocol.request_data and not ConnectLan.get_instance().is_logged_on():
                PassThroughWanProtocol.get_instance().handle_pass_through_callback(protocol.request_data)
            else:
                LogUtils.i(self.tag, "requestData is null or lan is connected")

        elif protocol.cmd == WanProtocolCmd.LOGOUT_GATEWAY:
            LogUtils.d(self.tag, "wan clear serverId.")
            GatewayInfo.get_instance().set_wan_server_code(None)

        elif protocol.cmd == WanProtocolCmd.GATEWAY_ONLINE:
            LogUtils.d(self.tag, "gateway online re get serverId.")
            WanDataHandleModel.get_instance().request_wan_server_id()

        elif protocol.cmd == WanProtocolCmd.GET_GATEWAY_SERVER:
            LogUtils.d(self.tag, "wan get serverId.")
            WanDataHandleModel.get_instance().response_wan_server_id(protocol)

        elif protocol.cmd == WanProtocolCmd.GATEWAY_REPLACE_STATE:
            state = protocol.request_data_body[0]
            LogUtils.d(self.tag, f"wan update gateway replace state. state value : {state}")

            # if state == 3:
            #     event = GatewayReplaceStateEvent(is_replace_success=False)
            #     RxBus.get_instance().post(event)
            # elif state == 4:
            #     GatewayDaoModel.get_instance().delete_current_gateway_data()
            #     event = GatewayReplaceStateEvent(is_replace_success=True, is_download_data=True)
            #     RxBus.get_instance().post(event)
            # elif state == 15:
            #     event = GatewayReplaceStateEvent(is_replace_success=True, is_download_data=False)
            #     RxBus.get_instance().post(event)

    def add_request(self, data: bytes) -> None:
        with threading.Lock():
            src = ConvertUtils.get_long_address_by_type(DeviceType.APP, User.get_instance().get_account_id())
            dest = GatewayInfo.get_instance().get_gateway_desc()

            if len(src) != 8:
                LogUtils.w(self.tag, "source invalid.")
                return

            server_code = GatewayInfo.get_instance().get_wan_server_code()
            default_id = ProtocolDefault.DEFAULT_WAN_SERVER_ID

            try:
                if server_code == default_id:
                    LogUtils.d(self.tag, "addRequest() get wan server id")
                    self.m_is_get_request_server_id = True
                    WanDataHandleModel.get_instance().request_wan_server_id()
                    return
            except Exception as e:
                LogUtils.e(self.tag, str(e))
                return

            if dest and len(dest) == 8:
                protocol = PassThroughWanProtocol.get_instance()
                protocol.set_lan_data(data)
                protocol.set_src_dest(src, dest)
                self.send_data(protocol.get_request_data())
            else:
                LogUtils.w(self.tag, "dest invalid.")

    def create_heartbeat_data(self) -> bytes:
        src = ConvertUtils.get_long_address_by_type(DeviceType.APP, User.get_instance().get_account_id())
        dest = ConvertUtils.get_long_address_by_type(DeviceType.SERVER, 0)
        return HeartWanProtocol.get_instance().get_request_data(src, dest)

    def handle_recv_data(self, data: bytes) -> None:
        if not data:
            LogUtils.e(self.tag, "data == null")
            return

        if len(data) > 0 and len(data) == (data[0] & 0xFF):
            self.handle_protocol_data(BaseWanProtocol.parse(data))
        else:
            DataPkgUtils.push_wan(data)
            protocols = DataPkgUtils.pull_wan()

            if protocols:
                for protocol in protocols:
                    self.handle_protocol_data(protocol)
            else:
                LogUtils.i(self.tag, "DataPkgUtils.pullWan() nothing, return.")

    def on_connect_result(self, success: bool) -> None:
        if success and self.m_socket:
            try:
                self.m_socket.settimeout(0)
            except socket.error as e:
                LogUtils.e(self.tag, str(e))
            self.logon()
        else:
            self.connect()

    def on_server_host_empty(self) -> None:
        LogUtils.i(self.tag, "onServerHostEmpty")

    def reset_wan(self) -> None:
        #
        self.reset()
        # DefaultThreadPool.get_instance().execute(lambda: self.reset())

    def send_heartbeat(self, data: bytes) -> None:
        super().send_heartbeat(data)

    def send_logon_data(self) -> None:
        LogUtils.i(self.tag, "sendLogonData")
        if not User.get_instance().is_project_account():
            protocol = LoginWanProtocol.get_instance()
            protocol.set_app_user(User.get_instance().get_username())
            protocol.set_app_pwd(User.get_instance().get_password())
            protocol.set_logon_mark(0)

            src = ConvertUtils.get_long_address_by_type(DeviceType.APP, User.get_instance().get_account_id())
            dest = GatewayInfo.get_instance().get_gateway_desc()
            data = protocol.get_request_data(src, dest)

            self.set_logon_state(LogonState.LOGGING_ON)
            self.send_data(data)

    def set_get_request_server_id(self) -> None:
        self.m_is_get_request_server_id = False
