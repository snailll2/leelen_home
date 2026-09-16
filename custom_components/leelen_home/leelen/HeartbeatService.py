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
        # 用 _is_service_destroy 命名,避免遮蔽下面的 is_service_destroy() 方法
        self._is_service_destroy = False
        self.connect_lan = None
        self.connect_wan = None
        self.no_intent = False
        self.hass = hass

    @classmethod
    def get_instance(cls) -> 'HeartbeatService':
        if not cls._instance:
            with cls._lock:
                if not cls._instance:
                    cls._instance = HeartbeatService()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """释放单例,供 HA 卸载/重载时清理,避免复用旧 hass/连接引用"""
        with cls._lock:
            if cls._instance is not None:
                inst = cls._instance
                cls._instance = None
                inst._is_service_destroy = True

    def can_conn_lan(self):
        return True

    def lan_conn_create(self, binding=False):
        from .ConnectLan import ConnectLan
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

    def wan_conn_close(self):
        LogUtils.i("wanConnClose")
        if self.connect_wan:
            self.connect_wan.close()
            self.connect_wan = None
            # 释放单例,避免重载复用旧 socket/线程
            from .ConnectWan import ConnectWan
            ConnectWan.reset_instance()

    def wan_conn_open(self):
        from .ConnectWan import ConnectWan
        LogUtils.i("wanConnOpen")
        if not self.connect_wan:
            self.connect_wan = ConnectWan.get_instance()
        if self.connect_wan:
            self.connect_wan.close()
            self.connect_wan.open()

    def wan_conn_reopen(self):
        LogUtils.i("wanConnReOpen")
        if not self.connect_wan:
            self.wan_conn_open()
        else:
            # 修复缺括号:原代码 is_project_account 恒真,导致重开 WAN 永不执行
            if User.get_instance().is_project_account():
                return
            self.connect_wan.set_connect_state(ConnectState.NONE)
            self.connect_wan.open()

    def is_service_destroy(self):
        return self._is_service_destroy

    def reset_and_restart(self):
        """重置并重新启动所有连接"""
        LogUtils.i("Resetting and restarting all connections")

        # 1. 关闭现有连接
        self.lan_conn_close()

        # 2. 重置状态
        self._is_service_destroy = False

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
        LogUtils.i(self.TAG, "lanConnClose")
        if self.connect_lan:
            self.connect_lan.close()
            self.connect_lan = None
            # 释放单例,避免重载复用旧 socket/线程
            from .ConnectLan import ConnectLan
            ConnectLan.reset_instance()

    def lan_conn_reopen(self):
        LogUtils.i(self.TAG, "lanConnReOpen")
        if not self.can_conn_lan():
            LogUtils.w(self.TAG, "canConnLan return false, abort.")
            return

        if not self.connect_lan:
            self.lan_conn_create(False)
            self.connect_lan.set_connect_state(ConnectState.NONE)
            self.connect_lan.open()
        else:
            if self.connect_lan.get_connect_state() == ConnectState.CONNECTED:
                return
            LogUtils.d(self.TAG, f"lanConnReOpen() connect lan state: {self.connect_lan.get_connect_state()}")
            self.connect_lan.set_connect_state(ConnectState.NONE)
            self.connect_lan.open()

    def create(self):
        HeartbeatService._instance = self
        self._is_service_destroy = False

    def request(self, data):
        try:
            self.connect_lan.add_request(data)
        except Exception as e:
            # 发送失败要可见,便于排查命令丢失
            LogUtils.w(f"request send failed: {e}")
