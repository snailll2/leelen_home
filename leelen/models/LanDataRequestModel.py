import logging
from threading import Lock

from ..HeartbeatService import HeartbeatService
from ..common import DeviceType
from ..common import LeelenConst
from ..entity.GatewayInfo import GatewayInfo
from ..entity.User import User
from ..entity.req.ConfigLockReq import ConfigLockReq
from ..entity.req.FetchConfigModReq import FetchConfigModReq
from ..entity.req.LoginReq import LoginReq
from ..protocols.FetchModConfigLanProtocol import FetchModConfigLanProtocol
from ..protocols.GetDeviceStatusLanProtocol import GetDeviceStatusLanProtocol
from ..protocols.LoginLanProtocol import LoginLanProtocol
from ..protocols.QueryModConfigLanProtocol import QueryModConfigLanProtocol
from ..protocols.RandomLanProtocol import RandomLanProtocol
from ..utils.ConvertUtils import ConvertUtils
from ..utils.EncodeUtil import EncodeUtil
from ..utils.LogUtils import LogUtils


class LanDataRequestModel:
    TAG = "LanDataRequestModel"
    _instance = None
    _lock = Lock()

    def __init__(self):
        pass

    def fetch_device_state_data(self, clear_data):
        LogUtils.d(f"{self.TAG}: fetchDeviceStateData()")

        fetch_req = FetchConfigModReq()
        fetch_req.tbl = "dev_state_tbl"
        fetch_req.num = 100
        fetch_req.type = "ins"
        fetch_req.T1 = 0
        fetch_req.T2 = ConvertUtils.to_long(LeelenConst.FF_BYTE)
        self.request_config_fetch(fetch_req)

    def fetch_logic_server_state_data(self, clear_data):
        with self._lock:
            LogUtils.d(f"{self.TAG}: fetchLogicServerStateData()")

            fetch_req = FetchConfigModReq()
            fetch_req.tbl = "logic_srv_state_tbl"
            fetch_req.num = 100
            fetch_req.type = "ins"
            fetch_req.T1 = 0
            fetch_req.T2 = ConvertUtils.to_long(LeelenConst.FF_BYTE)
            self.request_config_fetch(fetch_req)

    def fetch_sensor_state_data(self, clear_data):
        LogUtils.d(f"{self.TAG}: fetchSensorStateData()")

        fetch_req = FetchConfigModReq()
        fetch_req.tbl = "sensor_active_state_tbl"
        fetch_req.num = 100
        fetch_req.type = "ins"
        fetch_req.T1 = 0
        fetch_req.T2 = ConvertUtils.to_long(LeelenConst.FF_BYTE)
        self.request_config_fetch(fetch_req)

    @classmethod
    def get_instance(cls):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = cls()
        return cls._instance

    def get_state_data(self):
        gateway_desc = GatewayInfo.get_instance().get_gateway_desc_string()
        clear_data = True

        self.fetch_device_state_data(clear_data)
        self.fetch_logic_server_state_data(clear_data)
        self.fetch_sensor_state_data(clear_data)

    # def request_bind(self, gateway_name, group_id):
    #     connect_lan = ConnectLan.get_instance()
    #     bind_req = BindGatewayReq()
    #     bind_req.gateway_name = gateway_name
    #     bind_req.group_id = group_id
    #     bind_req.account = User.get_instance().get_username()
    #     bind_req.password = User.get_instance().get_password().lower()
    #     device_type = DeviceType.APP
    #     bind_req.app_id = ConvertUtils.bytes_to_hex(
    #         ConvertUtils.get_long_address_by_type(device_type, User.get_instance().get_account_id())
    #     )
    #     bind_protocol = BindGatewayLanProtocol()
    #     bind_protocol.set_bind_req(bind_req)
    #     connect_lan.send_data(
    #         bind_protocol.get_request_data(
    #             ConvertUtils.get_long_address_by_type(device_type, 0),
    #             GatewayInfo.get_instance().get_temp_gateway_desc(),
    #             None
    #         )
    #     )

    def request_config_fetch(self, fetch_req):
        LogUtils.d(f"{self.TAG}: requestConfigFetch() FetchConfigModReq: {fetch_req}")

        src_addr = ConvertUtils.get_long_address_by_type(
            DeviceType.APP,
            User.get_instance().get_account_id()
        )
        dst_addr = GatewayInfo.get_instance().get_gateway_desc()
        FetchModConfigLanProtocol.get_instance().set_fetch_config_mod_req(fetch_req)
        data = FetchModConfigLanProtocol.get_instance().get_request_data(src_addr, dst_addr, None)

        # LogUtils.e(f"{self.TAG}: requestConfigFetch() FetchConfigModReq: {data.hex()}")

        HeartbeatService.get_instance().request(data)

    def request_config_fetch_list(self, fetch_reqs):
        with self._lock:
            try:

                long_address = ConvertUtils.get_long_address_by_type(DeviceType.APP,
                                                                     User.get_instance().get_account_id())
                gateway_desc = GatewayInfo.get_instance().get_gateway_desc()

                for fetch_req in fetch_reqs:
                    LogUtils.d(self.TAG,
                               f"config fetch ack request tbl ： {fetch_req.tbl}, type : {fetch_req.type}, "
                               f"num: {fetch_req.num}, T1: {fetch_req.T1}, T2: {fetch_req.T2}")
                    FetchModConfigLanProtocol.get_instance().set_fetch_config_mod_req(fetch_req)
                    data = FetchModConfigLanProtocol.get_instance().get_request_data(long_address, gateway_desc, None)
                    HeartbeatService.get_instance().request(data)

            except Exception as e:
                logging.error(f"Error in request_config_fetch_list: {e}")

    def request_config_lock(self, lock):
        lock_req = ConfigLockReq()

        if lock:
            lock_req.time = 100
            lock_req.op = 0
        else:
            lock_req.time = 600
            lock_req.op = 1
        #
        # lock_protocol = ConfigLockLanProtocol.get_instance()
        # lock_protocol.set_config_lock_req(lock_req)
        #
        # data = lock_protocol.get_request_data(
        #     ConvertUtils.get_long_address_by_type(
        #         DeviceType.APP,
        #         User.get_instance().get_account_id()
        #     ),
        #     GatewayInfo.get_instance().get_gateway_desc(),
        #     None
        # )
        # HeartbeatService.get_instance().request(data)
        # return ConvertUtils.to_int(lock_protocol.frame_id)

    def request_config_query(self):
        with self._lock:
            LogUtils.d("TAG_GATEWAY: 向网关查询配置信息 requestConfigQuery()")
            LogUtils.d(f"{self.TAG}: requestConfigQuery()")

            src_addr = ConvertUtils.get_long_address_by_type(
                DeviceType.APP,
                User.get_instance().get_account_id()
            )
            dst_addr = GatewayInfo.get_instance().get_gateway_desc()
            data = QueryModConfigLanProtocol.get_instance().get_request_data(src_addr, dst_addr, None)

            # FrameIdSingleton.get_instance().set_frame_id(
            #     ConvertUtils.to_int(query_protocol.frame_id)
            # )
            # LanDataResponseHandleModel.get_instance().clear_req_table()
            HeartbeatService.get_instance().request(data)

    # def request_config_unlock(self):
    #     src_addr = ConvertUtils.get_long_address_by_type(
    #         DeviceType.APP,
    #         User.get_instance().get_account_id()
    #     )
    #     dst_addr = GatewayInfo.get_instance().get_gateway_desc()
    #     data = ConfigUnlockLanProtocol.get_instance().get_request_data(src_addr, dst_addr, None)
    #     HeartbeatService.get_instance().request(data)

    def request_device_status(self, device_addr):
        LogUtils.d(f"{self.TAG}: requestDeviceStatus() device address: {device_addr}")

        status_protocol = GetDeviceStatusLanProtocol.get_instance()
        addr_bytes = ConvertUtils.short_to_little_byte_array(device_addr)
        status_protocol.set_device_address(addr_bytes)

        data = status_protocol.get_request_data(
            ConvertUtils.get_long_address_by_type(
                DeviceType.APP,
                User.get_instance().get_account_id()
            ),
            GatewayInfo.get_instance().get_gateway_desc(),
            addr_bytes
        )
        HeartbeatService.get_instance().request(data)

    # def request_file_read(self, file_handle):
    #     ShortConnectLan.get_instance().connect(
    #         GatewayInfo.get_instance().get_lan_address_ip(),
    #         49154
    #     )
    #
    #     read_protocol = FileReadLanProtocol.get_instance()
    #     read_protocol.set_file_handle(ConvertUtils.int_to_little_byte_array(file_handle))
    #
    #     data = read_protocol.get_request_data(
    #         ConvertUtils.get_long_address_by_type(
    #             DeviceType.APP,
    #             User.get_instance().get_account_id()
    #         ),
    #         GatewayInfo.get_instance().get_gateway_desc(),
    #         None
    #     )
    #     ShortConnectLan.get_instance().send_data(data)

    def request_login(self, is_temp, random_key):
        from ..ConnectLan import ConnectLan
        password = User.get_instance().get_password()
        username = User.get_instance().get_username()

        logging.info(f"{self.TAG}: requestLogin()")

        if not password:
            logging.warning(f"{self.TAG}: getPassword == null, abort.")
            return

        if is_temp:
            password = EncodeUtil.get_md5("999999")
            src_addr = ConvertUtils.get_long_address_by_type(DeviceType.APP, 0)
            dst_addr = GatewayInfo.get_instance().get_temp_gateway_desc()
            username = "leelen"
        else:
            src_addr = ConvertUtils.get_long_address_by_type(
                DeviceType.APP,
                User.get_instance().get_account_id()
            )
            dst_addr = GatewayInfo.get_instance().get_gateway_desc()

        logging.info(f"{self.TAG}: userName value: {username}")

        password = password.lower()
        random_key = EncodeUtil.get_md5(f"{random_key}{password}").upper()

        login_req = LoginReq()
        login_req.random = random_key
        login_req.user_type = 1 if username == "leelen" else 0
        login_req.user = username
        # login_req.dev_type = 17 if AppInfoUtil.is_pad() else 16
        login_req.dev_type = 16
        login_req.DUID = GatewayInfo.get_instance().get_uid()

        LoginLanProtocol.get_instance().set_login_req(login_req)
        data = LoginLanProtocol.get_instance().get_request_data(src_addr, dst_addr, None)
        ConnectLan.get_instance().send_data(data)

    def request_random_key(self, is_temp):
        from ..ConnectLan import ConnectLan
        LogUtils.i(f"{self.TAG}: requestRandomKey()")

        if is_temp:
            src_addr = ConvertUtils.get_long_address_by_type(DeviceType.APP, 0)
            dst_addr = GatewayInfo.get_instance().get_temp_gateway_desc()
        else:
            src_addr = ConvertUtils.get_long_address_by_type(
                DeviceType.APP,
                User.get_instance().get_account_id()
            )
            dst_addr = GatewayInfo.get_instance().get_gateway_desc()

        data = RandomLanProtocol.get_instance().get_request_data(src_addr, dst_addr, None)

        ConnectLan.get_instance().send_data(data)
