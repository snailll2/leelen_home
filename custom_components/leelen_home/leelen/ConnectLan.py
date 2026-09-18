import time

from .BaseConnect import ConnectState, LogonState, BaseConnect
from .common import DeviceType
from .common.SingletonMixin import SingletonMixin
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

        if what == 0:  # unicast_result
            LogUtils.d(f"msg.what = unicast_result, result={arg1}")
            # self.connect_lan.on_unicast_listener(arg1 == 1)

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
                self.connect_lan.logon_fail_count = 0  # 登录成功,清空失败计数
                self.connect_lan.set_logon_state(LogonState.LOGGED_ON)
                # result_event = LoginLanResultEvent(login_suc=True, code=0)
                LogUtils.d("lan log on succeeded.")
                if not self.connect_lan.is_binding_gateway:
                    LogUtils.d("log on success then open heart and request config")
                    self.connect_lan.start_heartbeat()
                    User.get_instance().login_status = True
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
            # 修复:此前 logon_fail_count 从未累加,>=2 的封顶逻辑永远不触发,
            # 网关持续拒绝(ack=255)时就在 get_randomkey/logon_fail 间无限空转(~1ms 一次)。
            self.connect_lan.logon_fail_count += 1
            LogUtils.w(f"logonFailCount {self.connect_lan.logon_fail_count}")
            if self.connect_lan.logon_fail_count >= 2:
                self.connect_lan.logon_fail_count = 0
                DataPkgUtils.clear_lan_data()
                LogUtils.e("lan log on fail times exceed, close.")
                if GatewayInfo.get_instance().gateway_desc == GatewayInfo.get_instance().default_desc:
                    GatewayInfo.get_instance().reset()
                if hasattr(self.connect_lan, "reset_lan"):
                    self.connect_lan.reset_lan()
                else:
                    self.connect_lan.reset()

                # result_event = LoginLanResultEvent(login_suc=False, code=1)
                # RxBus.get_instance().post(result_event)
            else:
                # 修复:首次失败后退避 1s 再重试,避免对网关做 1ms 级请求风暴
                LogUtils.w("logon fail, backoff 1s before next random key request")
                time.sleep(1)
                self.connect_lan.send_logon_data()

    def send_empty_message(self, what):
        # 模拟发送一个空 message 回调自身
        self.handle_message(Message(what=what, arg1=0, obj=None))

    def remove_messages(self, what):
        # 如果你使用 asyncio/queue 或类似方式实现消息队列，可以补充这个方法
        pass

    def send(self, msg):
        self.handle_message(msg)


#: 已在协议里出现、但本移植未实现的网关上行指令(仅有日志的 case 桩)。
#: 键为 cmd(协议号),值为原实现里的日志文案;收到时按表打日志并忽略,
#: 未在表中的协议号则记一条 WARNING,便于发现新的指令类型。
UNHANDLED_RESPONSE_CMDS: dict[int, str] = {
    262: 'lan recv force quit',
    517: 'lan recv delete device hint ',
    518: 'lan recv device status update',
    521: 'lan recv sensor status',
    794: 'lan recv replace device status response',
    796: 'lan recv config import result notify',
    798: 'lan recv add service result',
    1027: 'lan recv device upgrade progress response',
    1416: 'lan recv gateway feedback protocol list',
    33028: 'lan recv heartbeat',
    33029: 'lan recv logout',
    33283: 'lan recv device control',
    33284: 'lan recv scene control',
    33285: 'lan recv device hint',
    33288: 'lan recv device control ex',
    33537: 'lan recv bind',
    33538: 'lan recv config common commit',
    33542: '处理配置锁返回',
    33543: 'lan recv config unlock',
    33544: 'lan recv config file import',
    33549: 'lan recv add floor',
    33550: 'lan recv add room',
    33551: 'lan recv create response',
    33552: 'lan recv linkage response',
    33553: 'lan recv time response',
    33554: 'lan recv delete physical device',
    33555: 'lan recv invite device',
    33556: 'lan recv sync time',
    33558: 'lan recv modify gatewayName',
    33560: 'lan recv replace device response',
    33561: 'lan recv replace device cancel response',
    33562: 'lan recv delete common message ',
    33565: 'lan recv add service response',
    33567: 'lan recv delete service response',
    33570: 'lan recv cancel device invite ',
    33572: 'lan recv get 485 protocol list',
    33573: 'lan recv add temporary password',
    33576: 'lan recv create arm',
    33577: 'lan recv create virtual response',
    33578: 'lan recv delete virtual response',
    33579: 'lan recv get real temporary password',
    33580: 'lan recv get lock member list',
    33581: 'lan recv get cloud status response',
    33583: 'lan recv get diy protocol list',
    33584: 'lan recv set diy protocol list',
    33585: 'lan recv get diy protocol',
    33587: 'lan recv update remote debug response',
    33588: 'lan recv get remote debug response',
    33796: 'lan recv device or gateway update response ',
    33797: 'lan recv device upgrade info response',
    34049: '处理添加红外转发器',
    34050: '处理添加红外转发器delete',
    34052: '增加wifi红外按键',
    34053: 'lan recv delete ir key',
    34054: '处理同步红外码库',
    34177: 'lan recv bind xiao bai',
    34178: 'lan recv bgm pass through data ',
    34179: 'lan recv manually add condition ',
    34180: "",
    34181: 'lan recv cancel gateway invite protocol list',
    34182: "",
    34185: 'lan recv gateway invite protocol list',
    34186: "",
    34187: "",
    34188: 'lan recv bind ipc protocol list',
    34189: 'lan recv unbind ipc protocol list',
    34190: 'lan recv add hope bgm device response',
    34192: 'lan recv smart panel add response',
    34193: 'lan recv screen support type response',
    34194: 'lan recv get screen quick control response',
    34195: 'lan recv set screen quick control response',
    34196: 'lan recv environment support type response',
    34197: 'lan recv get environment bind data response',
    34198: 'lan recv set environment bind data response',
    34199: 'lan recv submit custom skills response',
    34200: 'lan recv get custom skills response',
    34201: 'lan recv submit alarm skills response',
    34202: 'lan recv get alarm skills response',
    34203: 'lan recv set device_location response',
    34204: 'lan recv get device location response',
    34305: 'lan recv pass through app to device ',
    34307: 'lan recv file write req',
    34308: 'lan recv file read req',
    34311: 'lan recv local history',
}


class ConnectLan(SingletonMixin, BaseConnect):
    LOGON_FAIL_LIMIT = 2
    LOSS_HEARTBEAT_MAX_TIME = 3
    MSG_TYPE_GET_RANDOM_KEY = 1
    MSG_TYPE_LOGON_FAIL = 4
    MSG_TYPE_LOGON_RESULT = 2
    MSG_TYPE_LOGON_TIMEOUT = 3
    MSG_TYPE_UNICAST_RESULT = 0
    RECONNECT_MAX_TIME = 30

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
    def _on_reset(cls, instance):
        """释放单例前关闭 socket/线程,避免复用旧连接"""
        try:
            instance.close()
        except Exception as e:
            LogUtils.e(f"reset ConnectLan error: {e}")

    # @property
    def create_heartbeat_data(self):
        var1 = ConvertUtils.get_long_address_by_type(DeviceType.APP, User.get_instance().account_id)
        var2 = GatewayInfo.get_instance().gateway_desc
        return HeartLanProtocol().get_request_data(var1, var2, None)

    def on_connect_result(self, success: bool) -> None:
        if success:
            socket = self.socket  # Assuming mSocket is accessible as self.m_socket
            if socket is not None:
                try:
                    socket.settimeout(0)  # Set socket to blocking mode (no timeout)
                except Exception as e:
                    LogUtils.e("ConnectLan", f"设置 socket 阻塞模式失败: {e}")
                self.logon()
                return

        self.connect()

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


            case 33287:
                LogUtils.i(self.tag, "lan recv device status")
                # lanDataResponseHandleModel.handleGetDeviceStatus(baseLanProtocol);
                lanDataResponseHandleModel.handle_get_device_status(baseLanProtocol)
                return


            case 33027:
                LogUtils.i(self.tag, "lan recv login")
                lanDataResponseHandleModel.handle_login_lan_response(baseLanProtocol, self.mConnectHandler)
                return


            case 33026:
                LogUtils.i(self.tag, "lan recv random key")
                lanDataResponseHandleModel.handle_random_key_response(baseLanProtocol, self.mConnectHandler)
                return


            case 771:
                LogUtils.i(self.tag, "处理配置变更通知")
                lanDataResponseHandleModel.handle_config_modify_notify(baseLanProtocol);
                return


            case 514:
                LogUtils.i(self.tag, "lan recv dev status 设备状态 ")
                lanDataResponseHandleModel.handle_device_status(baseLanProtocol)
                # DeviceStatusLanProtocol.getInstance().updateDeviceStatus(baseLanProtocol);
                return


            case _:
                # 原实现是 84 个「只打日志就返回」的 case 桩,收敛为一张表 + 兜底分支。
                desc = UNHANDLED_RESPONSE_CMDS.get(cmd)
                if desc:
                    LogUtils.i(self.tag, desc)
                elif desc is None:
                    LogUtils.w(self.tag, f"lan recv 未识别协议号 {cmd},忽略")
                return
