from threading import Lock

from .BaseConnect import ConnectState
from .entity.User import User
from .utils.LogUtils import LogUtils


class HeartbeatService:
    MSG_TYPE_KEEP_ALIVE = 1
    MSG_TYPE_HTTP_LOGON = 2
    MSG_TYPE_TCP_LAN_LOGON = 3
    MSG_TYPE_HOUSE_REMOVED = 5
    MSG_TYPE_TASK_MOVE_TO_FRONT = 6
    MSG_TYPE_BIND_PROCESS = 7

    _instance = None
    _lock = Lock()
    TAG = "HeartbeatService"

    def __init__(self, hass=None):
        self.is_service_destroy = False
        self.connect_lan = None
        self.connect_wan = None
        self.no_intent = False
        self.hass = hass
        # LogUtils.logger = logging.getLogger(self.TAG)

    @classmethod
    def get_instance(cls) -> 'HeartbeatService':
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = HeartbeatService()
        return cls._instance

    def can_conn_lan(self):
        return True

    def lan_conn_create(self, binding=False):
        from .ConnectLan import ConnectLan
        with self._lock:
            username = User.get_instance().get_username()
            LogUtils.i(f"lanConnCreate() username {username}")

            if not self.can_conn_lan():
                LogUtils.w("canConnLan return false, abort.")
                return

            if not self.connect_lan:
                self.connect_lan = ConnectLan.get_instance()
            else:
                self.connect_lan.reset()

            if not self.connect_lan:
                LogUtils.w("mConnectLan == null, abort.")
                return

            if not username:
                LogUtils.w("param 'username' is null, abort.")
                return

            self.connect_lan.set_is_binding_gateway(binding)
            LogUtils.d(f"lan connect state: {self.connect_lan.get_connect_state()}")

            if not binding and self.connect_lan.get_connect_state() == ConnectState.CONNECTING:
                self.connect_lan.set_connect_state(ConnectState.NONE)

            self.connect_lan.set_connect_state(ConnectState.NONE)
            self.connect_lan.connect_lan()

    # def wan_conn_close(self):
    #     LogUtils.logger.info("wanConnClose")
    #     if self.connect_wan:
    #         self.connect_wan.close()
    #         self.connect_wan = None

    # def wan_conn_open(self):
    #     from .ConnectWan import ConnectWan
    #     LogUtils.logger.info("wanConnOpen")
    #     if not self.connect_wan:
    #         self.connect_wan = ConnectWan.get_instance()
    #     if self.connect_wan:
    #         self.connect_wan.close()
    #         self.connect_wan.open()

    # def wan_conn_reopen(self):
    #     LogUtils.logger.info("wanConnReOpen")
    #     if not self.connect_wan:
    #         self.wan_conn_open()
    #     else:
    #         if User.get_instance().is_project_account:
    #             return
    #         self.connect_wan.set_connect_state(ConnectState.NONE)
    #         self.connect_wan.open()

    def is_service_destroy(self):
        return self.is_service_destroy

    def reset_and_restart(self):
        """重置并重新启动所有连接"""
        LogUtils.i("Resetting and restarting all connections")
        
        # 1. 关闭现有连接
        self.lan_conn_close()
        
        # 2. 重置状态
        self.is_service_destroy = False
        
        # 3. 重新启动LAN连接
        try:
            self.lan_conn_create()
            # 4. 确保心跳服务启动
            if self.connect_lan:
                LogUtils.i("Starting heartbeat service")
                self.connect_lan.start_heartbeat()
            LogUtils.i("Reset and restart completed")
        except Exception as e:
            LogUtils.e(f"Error during reset and restart: {e}")

    def lan_conn_close(self):
        LogUtils.logger.info("lanConnClose")
        if self.connect_lan:
            self.connect_lan.close()
            self.connect_lan = None

    def lan_conn_reopen(self):
        LogUtils.logger.info("lanConnReOpen")
        if not self.can_conn_lan():
            LogUtils.logger.warning("canConnLan return false, abort.")
            return

        if not self.connect_lan:
            self.lan_conn_create(False)
            self.connect_lan.set_connect_state(ConnectState.NONE)
            self.connect_lan.open()
        else:
            if self.connect_lan.get_connect_state() == ConnectState.CONNECTED:
                return
            LogUtils.logger.debug(f"lanConnReOpen() connect lan state: {self.connect_lan.get_connect_state()}")
            self.connect_lan.set_connect_state(ConnectState.NONE)
            self.connect_lan.open()

    def create(self):
        HeartbeatService._instance = self
        self.is_service_destroy = False

    def request(self, data):
        try:
            # LogUtils.i(f"request in lan {data.hex()}")
            self.connect_lan.add_request(data)
        except Exception as e:
            LogUtils.d(e)
