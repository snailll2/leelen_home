"""Support for Leelen service."""
from __future__ import annotations

import asyncio
from types import MappingProxyType

from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import CoreState, Event, HomeAssistant

from .const import CONF_USERNAME, CONF_DEVICE_ADDR, CONF_ACCOUNT_ID, CONF_PASSWORD, CONF_GATEWAY_IP, DOMAIN
from .leelen.common.DefaultThreadPool import DefaultThreadPool
from .leelen.HeartbeatService import HeartbeatService
from .leelen.entity.GatewayInfo import GatewayInfo
from .leelen.entity.User import User
from .leelen.utils.LogUtils import LogUtils

_NOTIFICATION_ID = "leelen_connection_status"


class LeelenService:

    def __init__(self, hass: HomeAssistant, config: MappingProxyType) -> None:
        """Initialize."""
        self._hass = hass
        self._config = config
        self._monitor_task: asyncio.Task | None = None
        HeartbeatService.get_instance().hass = hass

    #
    async def async_start(self, config: dict[str, dict[str, str]]) -> None:
        User.get_instance().account_id = self._config.get(CONF_ACCOUNT_ID)
        User.get_instance().username = self._config.get(CONF_USERNAME)
        User.get_instance().password = self._config.get(CONF_PASSWORD)
        GatewayInfo.get_instance().set_gateway_desc(self._config.get(CONF_DEVICE_ADDR))
        GatewayInfo.get_instance().lan_address_ip = self._hass.data[DOMAIN].get(CONF_GATEWAY_IP)

        """Start the servcie, called when component starts."""
        LogUtils.i(f"{LeelenService.__name__} start async_start")

        def _start(event: Event | None = None):
            HeartbeatService.get_instance().lan_conn_create()
            LogUtils.i(f"{LeelenService.__name__} start HeartbeatService")

        if self._hass.state == CoreState.running:
            _start()
        else:
            # for situations when hass restarts
            self._hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _start)

        # 真实连接状态监控:lan_conn_create 之后连接/登录是后台线程异步进行的,
        # 不能在此时就发「已连接」通知(网关拒绝时尤其误导)。按现状滚动更新。
        self._start_connection_monitor()

    def _start_connection_monitor(self) -> None:
        """启动连接状态监控任务;覆盖重载前可能遗留的旧任务。"""
        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()
        self._monitor_task = self._hass.async_create_task(
            self._monitor_connection(), name="leelen_connection_monitor"
        )

    async def _monitor_connection(self) -> None:
        """轮询真实登录状态并更新「立林网关连接状态」通知。

        只用固定 notification_id 覆盖,状态未变化不重复发通知。
        连接关闭(connect_lan 置空)时发一次「已断开」并结束监控。
        """
        hs = HeartbeatService.get_instance()
        last_status: str | None = None
        while True:
            await asyncio.sleep(2)
            conn = hs.connect_lan
            if conn is None:
                # lan_conn_close 已把 connect_lan 置空 → stop 路径,结束监控
                if last_status != "disconnected":
                    await self._update_notification("disconnected")
                return
            if conn.is_logged_on():
                status = "connected"
            elif conn.logon_fail_count >= getattr(conn, "LOGON_FAIL_LIMIT", 2) or \
                    last_status == "failed":
                # 达到失败封顶,或已处于失败态(重置后仍在重试)保持失败提示
                status = "failed"
            else:
                status = "connecting"
            if status != last_status:
                await self._update_notification(status)
                last_status = status

    async def _update_notification(self, status: str) -> None:
        """按真实状态写/更新 persistent_notification(同一条,id 一致会覆盖)。"""
        addr = self._config.get(CONF_DEVICE_ADDR)
        ip = self._hass.data[DOMAIN].get(CONF_GATEWAY_IP)
        if status == "connected":
            message = f"网关{addr} ({ip}) 本地连接状态: 已连接"
        elif status == "failed":
            message = (
                f"网关{addr} ({ip}) 登录失败,正在重试。\n"
                "若持续失败,请检查「设备地址」是否正确、账号是否已在立林 App "
                "绑定该网关,并确认网关在线。"
            )
        elif status == "disconnected":
            message = f"网关{addr} ({ip}) 本地连接已断开。"
        else:  # connecting
            message = f"网关{addr} ({ip}) 正在连接..."
        await self._hass.services.async_call(
            "persistent_notification",
            "create",
            {
                "notification_id": _NOTIFICATION_ID,
                "message": message,
                "title": "立林网关连接状态",
            },
        )

    def stop(self) -> None:
        """Stop the service, called when component stops."""
        LogUtils.i(f"{LeelenService.__name__} stop")
        try:
            hs = HeartbeatService.get_instance()
            # 关闭 LAN/WAN 连接(内部会停止心跳/接收线程并关 socket,并各自释放单例)。
            # lan_conn_close 会把 connect_lan 置空,监控任务下一轮退出并提示已断开。
            hs.lan_conn_close()
            hs.wan_conn_close()
            # 重置线程池,释放工作线程,避免重载后旧线程残留。
            # 注意:不在 stop() 里重置 HeartbeatService 单例——async_restart() 也会走这里,
            # 重置会导致新实例 hass=None。hass 在下一次 setup 时会被 __init__ 刷新。
            DefaultThreadPool.reset_instance()
        except Exception as e:
            LogUtils.e(f"Stop error: {e}")

    async def async_restart(self):
        """重启服务"""
        LogUtils.i(f"{LeelenService.__name__} restarting")

        # 1. 停止当前服务(同步 stop 会 join 线程,放到执行器避免阻塞事件循环)
        await self._hass.async_add_executor_job(self.stop)

        # 2. 重置心跳服务
        HeartbeatService.get_instance().reset_and_restart()

        # 3. 重新启动服务
        await self.async_start({})

        LogUtils.i(f"{LeelenService.__name__} restart completed")