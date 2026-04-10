import threading
from typing import Optional

from ..BaseConnect import LogonState
from ..ConnectLan import ConnectLan
from ..common import DeviceType
from ..entity.GatewayInfo import GatewayInfo
from ..entity.User import User
from ..models.LanDataRequestModel import LanDataRequestModel
from ..protocols.GetServerCodeWanProtocol import GetServerCodeWanProtocol
from ..utils.ConvertUtils import ConvertUtils
from ..utils.DataPkgUtils import DataPkgUtils
from ..utils.LogUtils import LogUtils


class WanDataHandleModel:
    TAG = "WanDataHandleModel"
    _instance: Optional['WanDataHandleModel'] = None
    _lock = threading.Lock()

    def __init__(self):
        pass

    @classmethod
    def get_instance(cls) -> 'WanDataHandleModel':
        with cls._lock:
            if not cls._instance:
                cls._instance = WanDataHandleModel()
            return cls._instance

    def request_wan_server_id(self):
        from .ConnectWan import ConnectWan

        LogUtils.d(self.TAG, "request_wan_server_id()")
        protocol = GetServerCodeWanProtocol.get_instance()
        source = ConvertUtils.get_long_address_by_type(DeviceType.APP, User.get_instance().get_account_id())
        dest = GatewayInfo.get_instance().get_gateway_desc()
        ConnectWan.get_instance().send_data(protocol.get_request_data(source, dest))

    def response_login_other_place(self):
        from .ConnectWan import ConnectWan

        LogUtils.d(self.TAG, "response_login_other_place() post login other place event")
        User.get_instance().reset()
        logon_state = LogonState.NONE
        ConnectLan.get_instance().set_logon_state(logon_state)
        # ConnectWan.get_instance().set_logon_state(logon_state)
        ConnectLan.get_instance().close()
        ConnectWan.get_instance().close()
        DataPkgUtils.clear_lan_data()
        DataPkgUtils.clear_wan_data()
        GatewayInfo.get_instance().reset()

    def response_password_changed(self):
        from .ConnectWan import ConnectWan

        LogUtils.d(self.TAG, "response_password_changed() post password wrong event")
        User.get_instance().reset()
        logon_state = LogonState.NONE
        ConnectLan.get_instance().set_logon_state(logon_state)
        # ConnectWan.get_instance().set_logon_state(logon_state)
        ConnectLan.get_instance().close()
        ConnectWan.get_instance().close()
        DataPkgUtils.clear_lan_data()
        DataPkgUtils.clear_wan_data()
        GatewayInfo.get_instance().reset()

    def response_wan_server_id(self, protocol):
        if protocol.response_code == 1:
            data = protocol.request_data_body
            server_code = data[0:2]
            server_id = data[2:18]

            GatewayInfo.get_instance().set_wan_server_code(server_code)
            server_value = ConvertUtils.to_unsigned_short(server_code)

            LogUtils.d(self.TAG, f"response_wan_server_id() server value: {server_value}")

            request_model = LanDataRequestModel.get_instance()
            LogUtils.d(self.TAG, "response_wan_server_id() request_config_query()")
            request_model.get_state_data()
            request_model.request_config_query()

        from .ConnectWan import ConnectWan
        ConnectWan.get_instance().set_get_request_server_id()
