import threading

from .BaseConnect import ConnectState, LogonState, BaseConnect
from .common import DeviceType
from .entity.GatewayInfo import GatewayInfo
from .entity.Message import Message
from .entity.User import User
from .models.LanDataResponseHandleModel import LanDataResponseHandleModel
from .protocols.HeartLanProtocol import HeartLanProtocol
from .utils.ConvertUtils import ConvertUtils
from .utils.DataPkgUtils import DataPkgUtils
from .utils.LogUtils import LogUtils


class ConnectHandler:
    def __init__(self, connect_lan_instance):
        self.connect_lan = connect_lan_instance
        self.tag = connect_lan_instance.tag

    def handle_message(self, message):
        from .models.LanDataRequestModel import LanDataRequestModel

        LogUtils.i(f"connect handler handleMessage: {message.obj}")

        arg1 = message.arg1
        what = message.what
        result = False

        if what == 0:  # unicast_result
            LogUtils.d(f"msg.what = unicast_result, result={arg1}")
            result = arg1 == 1
            # self.connect_lan.on_unicast_listener(result)

        elif what == 1:  # get_randomkey
            LogUtils.d("msg.what = get_randomkey")
            LogUtils.d(f"serverHost value : {self.connect_lan.server_host}")
            key = message.obj
            if not key:
                self.send_empty_message(4)
            else:
                LanDataRequestModel.get_instance().request_login(
                    self.connect_lan.is_binding_gateway, key
                )

        elif what == 2:  # logon_result
            LogUtils.d(f"msg.what = logon_result, result={arg1}")
            self.remove_messages(3)
            if arg1 == 1:
                self.connect_lan.set_logon_state(LogonState.LOGGED_ON)
                # result_event = LoginLanResultEvent(login_suc=True, code=0)
                LogUtils.d("lan log on succeeded.")
                if not self.connect_lan.is_binding_gateway:
                    LogUtils.d("log on success then open heart and request config")
                    self.connect_lan.start_heartbeat()
                    User.get_instance().set_login_status(True)
                    User.get_instance().save()
                    model = LanDataRequestModel.get_instance()
                    model.request_config_query()
                    model.get_state_data()
                    
            else:
                LogUtils.w("lan log on failed.")
                self.send_empty_message(4)

        elif what == 3:  # logon_timeout
            LogUtils.d("msg.what = logon_timeout")
            self.send_empty_message(4)

        elif what == 4:  # logon_fail
            LogUtils.d("msg.what = logon_fail")
            self.connect_lan.set_logon_state(LogonState.NONE)
            LogUtils.d(f"logonFailCount {self.connect_lan.logon_fail_count}")
            if self.connect_lan.logon_fail_count >= 2:
                self.connect_lan.logon_fail_count = 0
                DataPkgUtils.clear_lan_data()
                LogUtils.e("lan log on fail times exceed, close.")
                if GatewayInfo.get_instance().get_gateway_desc() == GatewayInfo.get_instance().default_desc:
                    GatewayInfo.get_instance().reset()
                self.connect_lan.reset_lan()

                # result_event = LoginLanResultEvent(login_suc=False, code=1)
                # RxBus.get_instance().post(result_event)
            else:
                self.connect_lan.send_logon_data()

    def send_empty_message(self, what):
        # 模拟发送一个空 message 回调自身
        self.handle_message(Message(what=what, arg1=0, obj=None))

    def remove_messages(self, what):
        # 如果你使用 asyncio/queue 或类似方式实现消息队列，可以补充这个方法
        pass

    def send(self, msg):
        self.handle_message(msg)


class ConnectLan(BaseConnect):
    LOGON_FAIL_LIMIT = 2
    LOSS_HEARTBEAT_MAX_TIME = 3
    MSG_TYPE_GET_RANDOM_KEY = 1
    MSG_TYPE_LOGON_FAIL = 4
    MSG_TYPE_LOGON_RESULT = 2
    MSG_TYPE_LOGON_TIMEOUT = 3
    MSG_TYPE_UNICAST_RESULT = 0
    RECONNECT_MAX_TIME = 30

    _instance = None
    _lock = threading.Lock()
    mIsBindingGateway = False

    def __init__(self, server_host: str = None, server_port: int = 49153, username: str = None, password: str = None):
        super().__init__(server_host, server_port, username, password)
        self.tag = "🍺 ConnectLan:"
        self.server_host = None
        self.server_port = 49153
        self.heartbeat_interval = 5
        self.logon_fail_count = 0
        self.send_heartbeat_count = 0
        self.unicast_count = 0
        self.is_binding_gateway = True
        self.connect_state = ConnectState.NONE
        self.logon_state = LogonState.NONE
        self.pre_heartbeat_recv = False
        self.pre_heartbeat_send_time = 0
        self.socket = None
        # self.output_stream = None
        self.heartbeat_data = None
        self.mConnectHandler = ConnectHandler(self)

    @classmethod
    def get_instance(cls):
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = ConnectLan()
        return cls._instance

    # @property
    def create_heartbeat_data(self):
        var1 = ConvertUtils.get_long_address_by_type(DeviceType.APP, User.get_instance().get_account_id())
        var2 = GatewayInfo.get_instance().get_gateway_desc()
        return HeartLanProtocol.get_instance().get_request_data(var1, var2, None)

    def on_connect_result(self, success: bool) -> None:
        if success:
            socket = self.socket  # Assuming mSocket is accessible as self.m_socket
            if socket is not None:
                try:
                    socket.settimeout(0)  # Set socket to blocking mode (no timeout)
                except Exception as e:
                    import traceback
                    LogUtils.e(e)
                self.logon()
                return

        self.connect()

    def on_server_host_empty(self) -> None:
        """服务器地址为空时的回调"""
        LogUtils.w(self.tag, "Server host is empty, cannot connect to LAN device")

    def add_request(self, data):
        self.send_data(data)

    def reset(self):
        LogUtils.d(f"{self.tag} connect lan reset")
        
        # 1. 清理ConnectLan特有的状态
        self.send_heartbeat_count = 0
        self.logon_fail_count = 0
        self.unicast_count = 0
        self.heartbeat_data = None
        
        # 2. 调用父类reset方法（会清理socket、线程和其他状态）
        super().reset()
        
        # 3. 重置ConnectLan特有的状态
        if hasattr(self, 'connect_state'):
            self.connect_state = ConnectState.NONE
        if hasattr(self, 'logon_state'):
            self.logon_state = LogonState.NONE
        
        LogUtils.d(f"{self.tag} reset completed")

    def open(self):
        LogUtils.d(f"{self.tag} open() set server host value: {self.server_host}")
        self.unicast_count = 0
        self.heartbeat_data = self.create_heartbeat_data()
        super().open()

    def set_is_binding_gateway(self, binding):
        self.is_binding_gateway = binding

    def get_connect_state(self):
        return self.connect_state
    
    def get_logon_state(self):
        return self.logon_state
    
    def set_logon_state(self, state: LogonState):
        self.logon_state = state
    
    def set_connect_state(self, state: ConnectState):
        self.connect_state = state
    
    def get_is_binding_gateway(self):
        return self.is_binding_gateway
    
    def get_pre_heartbeat_recv(self):
        return self.pre_heartbeat_recv
    
    def set_pre_heartbeat_recv(self, recv: bool):
        self.pre_heartbeat_recv = recv
    
    def get_pre_heartbeat_send_time(self):
        return self.pre_heartbeat_send_time
    
    def set_pre_heartbeat_send_time(self, time: int):
        self.pre_heartbeat_send_time = time
    
    


    def send_logon_data(self):
        LogUtils.i(f"{self.tag}: sendLogonData {self.server_host}")

        if self.get_logon_state() == LogonState.LOGGING_ON:
            LogUtils.w(f"{self.tag}: still logging on, ignore.")
        else:
            self.set_logon_state(LogonState.LOGGING_ON)
            self.get_random_key()

    def get_random_key(self):
        # 模拟生成随机密钥
        LogUtils.d("Generating random key...")
        from .models.LanDataRequestModel import LanDataRequestModel
        LanDataRequestModel.get_instance().request_random_key(self.mIsBindingGateway)

    def handle_recv_data(self, data: bytes):
        from .utils.DataPkgUtils import DataPkgUtils

        if data is None:
            LogUtils.d(self.tag, "data == null")
        else:
            # LogUtils.d(f"📥 Received: {data.decode(errors='ignore')}")
            self.recv_heartbeat()
            DataPkgUtils.push_lan(data)
            data_list = DataPkgUtils.pull_lan()

            if data_list:
                for protocol_data in data_list:
                    self.handle_protocol_data(protocol_data)
            else:
                LogUtils.i(self.tag, "DataPkgUtils.pullLan() nothing, return.")

    def handle_protocol_data(self, baseLanProtocol):
        if not baseLanProtocol:
            LogUtils.d(f"{self.tag} no protocol to handle.")
            return

        if not baseLanProtocol.request_data:
            LogUtils.d(f"{self.tag} no data to handle.")
            return

        if self.connect_state == ConnectState.CONNECTED:
            self.pre_heartbeat_recv = True

        # Handle different protocol types
        cmd = ConvertUtils.to_unsigned_short(baseLanProtocol.cmd)
        LogUtils.d(f"📥 Received: protocol.cmd {cmd}, {baseLanProtocol.request_data_body}")
        # LogUtils.d(json.loads(baseLanProtocol.request_data_body))
        lanDataResponseHandleModel = LanDataResponseHandleModel.get_instance()
        # LogUtils.d(self.tag, f">>>>>>>>>>protocol.cmd {cmd} match .<<<")
        match cmd:
            # default:
            #     #LogUtils.e(self.tag, ">>>protocol.cmd match none.<<<")
            #     ConvertUtils.LogUtils.dByteArr(self.tag, "protocol.cmd", baseLanProtocol.cmd);
            #     return

            case 34311:
                LogUtils.i(self.tag, "lan recv local history")
                #                 lanDataResponseHandleModel.handleLocalHistoryPassThroughResponse(baseLanProtocol);
                return

            case 34308:
                LogUtils.i(self.tag, "lan recv file read req")
                # lanDataResponseHandleModel.handleFileReadOrWriteReq(baseLanProtocol, true);
                return

            case 34307:
                LogUtils.i(self.tag, "lan recv file write req")
                # lanDataResponseHandleModel.handleFileReadOrWriteReq(baseLanProtocol, false);
                return

            case 34305:
                LogUtils.i(self.tag, "lan recv pass through app to device ")
                # lanDataResponseHandleModel.handleAppDevicePassThroughResponse(baseLanProtocol);
                return

            case 34204:
                LogUtils.i(self.tag, "lan recv get device location response")
                # lanDataResponseHandleModel.handleGetDeviceLocation(baseLanProtocol);
                return

            case 34203:
                LogUtils.i(self.tag, "lan recv set device_location response")
                # lanDataResponseHandleModel.handleSetDeviceLocation(baseLanProtocol);
                return

            case 34202:
                LogUtils.i(self.tag, "lan recv get alarm skills response")
                # lanDataResponseHandleModel.handleGetVoiceAlarm(baseLanProtocol);
                return

            case 34201:
                LogUtils.i(self.tag, "lan recv submit alarm skills response")
                # lanDataResponseHandleModel.handleSubmitVoiceAlarm(baseLanProtocol);
                return

            case 34200:
                LogUtils.i(self.tag, "lan recv get custom skills response")
                # lanDataResponseHandleModel.handleGetVoiceSkill(baseLanProtocol);
                return

            case 34199:
                LogUtils.i(self.tag, "lan recv submit custom skills response")
                # lanDataResponseHandleModel.handleSubmitVoiceSkill(baseLanProtocol);
                return

            case 34198:
                LogUtils.i(self.tag, "lan recv set environment bind data response")
                # lanDataResponseHandleModel.handleSetEnvironmentBindDataResponse(baseLanProtocol);
                return

            case 34197:
                LogUtils.i(self.tag, "lan recv get environment bind data response")
                # lanDataResponseHandleModel.handleGetEnvironmentBindData(baseLanProtocol);
                return

            case 34196:
                LogUtils.i(self.tag, "lan recv environment support type response")
                # lanDataResponseHandleModel.handleEnvironmentSupportType(baseLanProtocol);
                return

            case 34195:
                LogUtils.i(self.tag, "lan recv set screen quick control response")
                # lanDataResponseHandleModel.handleSetQuickControlData(baseLanProtocol);
                return

            case 34194:
                LogUtils.i(self.tag, "lan recv get screen quick control response")
                # lanDataResponseHandleModel.handleGetQuickControlData(baseLanProtocol);
                return

            case 34193:
                LogUtils.i(self.tag, "lan recv screen support type response")
                # lanDataResponseHandleModel.handleQuickControlSupportType(baseLanProtocol);
                return

            case 34192:
                LogUtils.i(self.tag, "lan recv smart panel add response")
                # lanDataResponseHandleModel.handleSmartPanelAdd(baseLanProtocol);
                return

            case 34190:
                LogUtils.i(self.tag, "lan recv add hope bgm device response")
                # lanDataResponseHandleModel.handleAddHopeBgmDeviceResponse(baseLanProtocol);
                return

            case 34187:
                return
            case 34189:
                LogUtils.i(self.tag, "lan recv unbind ipc protocol list")
                # lanDataResponseHandleModel.handleIpcUnBindLanResponse(baseLanProtocol);
                return

            case 34186:
                return
            case 34188:
                LogUtils.i(self.tag, "lan recv bind ipc protocol list")
                # lanDataResponseHandleModel.handleIpcBindLanResponse(baseLanProtocol);
                return

            case 34181:
                LogUtils.i(self.tag, "lan recv cancel gateway invite protocol list")
                # lanDataResponseHandleModel.handleCancelGatewayDevice(baseLanProtocol);
                return

            case 34180:
                return
            case 34182:
                return
            case 34185:
                LogUtils.i(self.tag, "lan recv gateway invite protocol list")
                # lanDataResponseHandleModel.handleGatewayDevice(baseLanProtocol);
                return

            case 34179:
                LogUtils.i(self.tag, "lan recv manually add condition ")
                # lanDataResponseHandleModel.handleManuallyAddCondition(baseLanProtocol);
                return

            case 34178:
                LogUtils.i(self.tag, "lan recv bgm pass through data ")
                # lanDataResponseHandleModel.handleBgmPassThroughData(baseLanProtocol);
                return

            case 34177:
                LogUtils.i(self.tag, "lan recv bind xiao bai")
                # lanDataResponseHandleModel.handleBindXiaoBai(baseLanProtocol);
                return

            case 34054:
                LogUtils.i(self.tag, "处理同步红外码库")
                # lanDataResponseHandleModel.handleSyncIrCode(baseLanProtocol);
                return
            case 34053:
                LogUtils.i(self.tag, "lan recv delete ir key")
                # lanDataResponseHandleModel.handleDeleteIrKey(baseLanProtocol);
                return
            case 34052:
                LogUtils.i(self.tag, "增加wifi红外按键")
                # lanDataResponseHandleModel.handleCreateIrKey(baseLanProtocol);
                return
            case 34050:
                LogUtils.i(self.tag, "处理添加红外转发器delete")
                # lanDataResponseHandleModel.handleCreateOrDeleteIrDevice(baseLanProtocol, false);
                return
            case 34049:
                LogUtils.i(self.tag, "处理添加红外转发器")
                # lanDataResponseHandleModel.handleCreateOrDeleteIrDevice(baseLanProtocol, true);
                return
            case 33797:
                LogUtils.i(self.tag, "lan recv device upgrade info response")
                # lanDataResponseHandleModel.handleDeviceUpgradeInfoResponse(baseLanProtocol);
                return

            case 33796:
                LogUtils.i(self.tag, "lan recv device or gateway update response ")
                return

            case 33588:
                LogUtils.i(self.tag, "lan recv get remote debug response")
                # lanDataResponseHandleModel.handleGetRemoteDebug(baseLanProtocol);
                return

            case 33587:
                LogUtils.i(self.tag, "lan recv update remote debug response")
                # lanDataResponseHandleModel.handleUpdateRemoteDebug(baseLanProtocol);
                return

            case 33585:
                LogUtils.i(self.tag, "lan recv get diy protocol")
                # lanDataResponseHandleModel.handleGetDiyProtocol(baseLanProtocol);
                return

            case 33584:
                LogUtils.i(self.tag, "lan recv set diy protocol list")
                # lanDataResponseHandleModel.handleSetDiyProtocolList(baseLanProtocol);
                return

            case 33583:
                LogUtils.i(self.tag, "lan recv get diy protocol list")
                # lanDataResponseHandleModel.handleGetDiyProtocolList(baseLanProtocol);
                return

            case 33581:
                LogUtils.i(self.tag, "lan recv get cloud status response")
                # lanDataResponseHandleModel.handleGetCloudStatus(baseLanProtocol);
                return

            case 33580:
                LogUtils.i(self.tag, "lan recv get lock member list")
                # lanDataResponseHandleModel.handleGetLockMemberListResponse(baseLanProtocol);
                return

            case 33579:
                LogUtils.i(self.tag, "lan recv get real temporary password")
                # lanDataResponseHandleModel.handleGetRealTemporaryPasswordResponse(baseLanProtocol);
                return

            case 33578:
                LogUtils.i(self.tag, "lan recv delete virtual response")
                # lanDataResponseHandleModel.handleDeleteVirtualResponse(baseLanProtocol);
                return

            case 33577:
                LogUtils.i(self.tag, "lan recv create virtual response")
                # lanDataResponseHandleModel.handleCreateVirtualResponse(baseLanProtocol);
                return

            case 33576:
                LogUtils.i(self.tag, "lan recv create arm")
                # lanDataResponseHandleModel.handleCreateArm(baseLanProtocol);
                return

            case 33573:
                LogUtils.i(self.tag, "lan recv add temporary password")
                # lanDataResponseHandleModel.handleAddTemporaryPasswordResponse(baseLanProtocol);
                return

            case 33572:
                LogUtils.i(self.tag, "lan recv get 485 protocol list")
                # lanDataResponseHandleModel.handleGet485ProtocolList(baseLanProtocol);
                return

            case 33570:
                LogUtils.i(self.tag, "lan recv cancel device invite ")
                return

            case 33567:
                LogUtils.i(self.tag, "lan recv delete service response")
                # lanDataResponseHandleModel.handleDeleteService(baseLanProtocol);
                return

            case 33565:
                LogUtils.i(self.tag, "lan recv add service response")
                # lanDataResponseHandleModel.handleAddService(baseLanProtocol);
                return

            case 33562:
                LogUtils.i(self.tag, "lan recv delete common message ")
                # lanDataResponseHandleModel.handleDeleteCommonMsg(baseLanProtocol);
                return

            case 33561:
                LogUtils.i(self.tag, "lan recv replace device cancel response")
                return

            case 33560:
                LogUtils.i(self.tag, "lan recv replace device response")
                # lanDataResponseHandleModel.handleDeviceReplace(baseLanProtocol);
                return

            case 33558:
                LogUtils.i(self.tag, "lan recv modify gatewayName")
                # lanDataResponseHandleModel.handleModifyGatewayName(baseLanProtocol);
                return

            case 33556:
                LogUtils.i(self.tag, "lan recv sync time")
                return

            case 33555:
                LogUtils.i(self.tag, "lan recv invite device")
                # lanDataResponseHandleModel.handleDeviceInvite(baseLanProtocol);
                return

            case 33554:
                LogUtils.i(self.tag, "lan recv delete physical device")
                # lanDataResponseHandleModel.handleDeviceDelete(baseLanProtocol);
                return

            case 33553:
                LogUtils.i(self.tag, "lan recv time response")
                # lanDataResponseHandleModel.handleCreateTimer(baseLanProtocol);
                return

            case 33552:
                LogUtils.i(self.tag, "lan recv linkage response")
                # lanDataResponseHandleModel.handleCreateLinkage(baseLanProtocol);
                return

            case 33551:
                LogUtils.i(self.tag, "lan recv create response")
                # lanDataResponseHandleModel.handleCreateScene(baseLanProtocol);
                return

            case 33550:
                LogUtils.i(self.tag, "lan recv add room")
                # lanDataResponseHandleModel.handleCreateRoom(baseLanProtocol);
                return

            case 33549:
                LogUtils.i(self.tag, "lan recv add floor")
                # lanDataResponseHandleModel.handleCreateFloor(baseLanProtocol);
                return

            case 33544:
                LogUtils.i(self.tag, "lan recv config file import")
                # lanDataResponseHandleModel.handleConfigFileImport(baseLanProtocol);
                return

            case 33543:
                LogUtils.i(self.tag, "lan recv config unlock")
                return

            case 33542:
                LogUtils.i(self.tag, "处理配置锁返回")
                # lanDataResponseHandleModel.handleConfigLock(baseLanProtocol);
                return
            case 33541:
                # LogUtils.i(self.tag, "处理获取配置信息返回2")
                LogUtils.i(self.tag, f"处理获取配置信息返回2 TODO！！！！{baseLanProtocol.request_data_body}")
                lanDataResponseHandleModel.handle_config_fetch_response(baseLanProtocol);
                # lanDataResponseHandleModel.handleConfigFetchResponse(baseLanProtocol);
                return
            case 33540:
                LogUtils.i(self.tag, "处理查询配置信息返回")
                lanDataResponseHandleModel.handle_config_query_response(baseLanProtocol)
                return

            case 33538:
                LogUtils.i(self.tag, "lan recv config common commit")
                # lanDataResponseHandleModel.handleCommonCommitConfig(baseLanProtocol);
                return

            case 33537:
                LogUtils.i(self.tag, "lan recv bind")
                # lanDataResponseHandleModel.handleBindLanResponse(baseLanProtocol);
                return

            case 33288:
                LogUtils.i(self.tag, "lan recv device control ex")
                # lanDataResponseHandleModel.handleControlDevice(baseLanProtocol);
                return

            case 33287:
                LogUtils.i(self.tag, "lan recv device status")
                # lanDataResponseHandleModel.handleGetDeviceStatus(baseLanProtocol);
                lanDataResponseHandleModel.handle_get_device_status(baseLanProtocol)
                return

            case 33285:
                LogUtils.i(self.tag, "lan recv device hint")
                # lanDataResponseHandleModel.handleDeviceHint(baseLanProtocol);
                return

            case 33284:
                LogUtils.e(self.tag, "lan recv scene control")
                # lanDataResponseHandleModel.handleControlScene(baseLanProtocol);
                return

            case 33283:
                LogUtils.i(self.tag, "lan recv device control")
                # lanDataResponseHandleModel.handleControlDevice(baseLanProtocol);
                return

            case 33029:
                LogUtils.i(self.tag, "lan recv logout")
                # lanDataResponseHandleModel.handleLogoutResponse(baseLanProtocol);
                return

            case 33028:
                LogUtils.d(self.tag, "lan recv heartbeat")
                return

            case 33027:
                LogUtils.i(self.tag, "lan recv login")
                lanDataResponseHandleModel.handle_login_lan_response(baseLanProtocol, self.mConnectHandler)
                return

            case 33026:
                LogUtils.i(self.tag, "lan recv random key")
                lanDataResponseHandleModel.handle_random_key_response(baseLanProtocol, self.mConnectHandler)
                return

            case 1416:
                LogUtils.i(self.tag, "lan recv gateway feedback protocol list")
                # lanDataResponseHandleModel.handleGatewayFeedbackDevice(baseLanProtocol);
                return

            case 1027:
                LogUtils.i(self.tag, "lan recv device upgrade progress response")
                # lanDataResponseHandleModel.handleDeviceUpgradeProgressResponse(baseLanProtocol);
                return

            case 798:
                LogUtils.i(self.tag, "lan recv add service result")
                # lanDataResponseHandleModel.handleAddServiceResult(baseLanProtocol);
                return

            case 796:
                LogUtils.i(self.tag, "lan recv config import result notify")
                # lanDataResponseHandleModel.handleConfigImportResultNotify(baseLanProtocol);
                return

            case 794:
                LogUtils.i(self.tag, "lan recv replace device status response")
                # lanDataResponseHandleModel.handleDeviceReplaceStatus(baseLanProtocol);
                return

            case 771:
                LogUtils.i(self.tag, "处理配置变更通知")
                lanDataResponseHandleModel.handle_config_modify_notify(baseLanProtocol);
                return

            case 521:
                LogUtils.i(self.tag, "lan recv sensor status")
                # lanDataResponseHandleModel.handleUpdateSensorStatus(baseLanProtocol);
                return

            case 518:
                LogUtils.i(self.tag, "lan recv device status update")
                # lanDataResponseHandleModel.handleUpdateDeviceStatus(baseLanProtocol);
                return

            case 517:
                LogUtils.i(self.tag, "lan recv delete device hint ")
                return

            case 514:
                LogUtils.i(self.tag, f"lan recv dev status 设备状态 ")
                lanDataResponseHandleModel.handle_device_status(baseLanProtocol)
                # DeviceStatusLanProtocol.getInstance().updateDeviceStatus(baseLanProtocol);
                return

            case 262:

                LogUtils.i(self.tag, "lan recv force quit")
                #                this.forceLogout();
                return
