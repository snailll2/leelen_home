"""Support for Leelen service."""
from __future__ import annotations

import asyncio
import logging
from types import MappingProxyType

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import CoreState, Event, HomeAssistant

from .const import CONF_USERNAME, CONF_DEVICE_ADDR, CONF_ACCOUNT_ID, CONF_PASSWORD, CONF_GATEWAY_IP, CONF_CONNECT_MODE, CONNECT_MODE_WAN, DEFAULT_CONNECT_MODE, DOMAIN
from .leelen.common.DefaultThreadPool import DefaultThreadPool
from .leelen.HeartbeatService import HeartbeatService
from .leelen.entity.GatewayInfo import GatewayInfo
from .leelen.entity.User import User
from .leelen.utils.LogUtils import LogUtils

_LOGGER = logging.getLogger(__name__)

_NOTIFICATION_ID = "leelen_connection_status"


class LeelenService:

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize."""
        self._hass = hass
        self._entry = entry
        self._config: MappingProxyType = entry.data
        self._monitor_task: asyncio.Task | None = None
        # 置位=stop() 已执行,监控任务据此区分「未启动/启动初期」与「真正停止」。
        self._monitor_stop = False
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

        # 连接方式:lan(Local)/wan(Internet),取自 options;决定 request() 的路由和启动哪一路连接。
        hs = HeartbeatService.get_instance()
        hs.request_mode = config.get(CONF_CONNECT_MODE, DEFAULT_CONNECT_MODE)
        LogUtils.i(f"{LeelenService.__name__} connect mode = {hs.request_mode}")

        def _start(event: Event | None = None):
            # WAN 模式只起 WAN,绝不起 LAN —— WAN 回包仅在 ConnectLan.is_logged_on()==False
            # 时被处理(ConnectWan.handle_protocol_data L105),LAN 登录成功会吞掉 WAN 回程。
            if hs.request_mode == CONNECT_MODE_WAN:
                hs.wan_conn_open()
            else:
                hs.lan_conn_create()
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
        """启动连接状态监控任务;覆盖重载前可能遗留的旧任务。

        必须用 entry.async_create_background_task:监控是常驻 while True 任务,
        用裸 async_create_task 会进入 bootstrap 的等待集合,每回开机都要等它
        超时才放行(HOMEASSISTANT_STARTED 被拖住,连接迟迟不建)。绑定 entry
        的后台任务不阻塞启动/停止,且卸载时自动取消。
        """
        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()
        # 重启后清掉停止标记:新连接建立后监控要能正常发「已连接」。
        self._monitor_stop = False
        self._monitor_task = self._entry.async_create_background_task(
            self._hass, self._monitor_connection(), name="leelen_connection_monitor"
        )

    async def _monitor_connection(self) -> None:
        """轮询真实登录状态并更新「立林网关连接状态」通知。

        只用固定 notification_id 覆盖,状态未变化不重复发通知。
        状态机:connected ⇄ disconnected/connecting/failed。
        注意:connect_lan is None 不一定代表已停止——启动初期登录挂在
        HOMEASSISTANT_STARTED 之后,connect_lan 短暂为 None;若此时发「已断开」
        并 return,之后登录/自愈成功将无人再发「已连接」,通知永久停在「已断开」。
        所以只有 _monitor_stop(unload/restart 的 stop() 置位)才结束任务。
        """
        hs = HeartbeatService.get_instance()
        last_status: str | None = None
        while True:
            await asyncio.sleep(2)
            # 按当前连接模式监控对应连接:WAN 模式看 connect_wan(connect_lan 恒 None),
            # LAN 模式看 connect_lan。
            only_wan = hs.request_mode == CONNECT_MODE_WAN
            conn = hs.connect_wan if only_wan else hs.connect_lan
            if conn is None:
                # 未停止且连接对象还没创建:继续轮询,不发任何通知
                if self._monitor_stop and last_status != "disconnected":
                    await self._update_notification("disconnected")
                    return
                continue
            if conn.is_logged_on():
                status = "connected"
            elif last_status == "connected":
                # 曾经已连接、现在退出登录态 → 真实断开(心跳超时/对端 RST)
                status = "disconnected"
            elif getattr(conn, "logon_fail_count", 0) >= getattr(conn, "LOGON_FAIL_LIMIT", 2) or \
                    last_status == "failed":
                # 达到失败封顶,或已处于失败态(重置后仍在重试)保持失败提示
                # 注意:logon_fail_count/LOGON_FAIL_LIMIT 只在 ConnectLan 上定义,
                # ConnectWan 没有 → 用 getattr 兜底,避免 WAN 模式下监控任务炸掉。
                status = "failed"
            else:
                status = "connecting"
            if status != last_status:
                await self._update_notification(status, only_wan)
                last_status = status

    async def _update_notification(self, status: str, only_wan: bool = False) -> None:
        """按真实状态写/更新 persistent_notification(同一条,id 一致会覆盖)。"""
        addr = self._config.get(CONF_DEVICE_ADDR)
        # unload 后 DOMAIN 可能已被 pop,读不到时按空值降级,避免 KeyError 炸掉监控任务。
        ip = self._hass.data.get(DOMAIN, {}).get(CONF_GATEWAY_IP)
        channel = "互联网" if only_wan else "本地"
        if status == "connected":
            message = f"网关{addr} ({ip}) {channel}连接状态: 已连接"
        elif status == "failed":
            message = (
                f"网关{addr} ({ip}) {channel}登录失败,正在重试。\n"
                "若持续失败,请检查「设备地址」是否正确、账号是否已在「小立管家」"
                "绑定该网关,并确认网关在线。"
            )
        elif status == "disconnected":
            message = f"网关{addr} ({ip}) {channel}连接已断开。"
        else:  # connecting
            message = f"网关{addr} ({ip}) {channel}正在连接..."
        try:
            await self._hass.services.async_call(
                "persistent_notification",
                "create",
                {
                    "notification_id": _NOTIFICATION_ID,
                    "message": message,
                    "title": "立林网关连接状态",
                },
            )
        except Exception:  # noqa: BLE001 - 通知失败不应弄死整个监控任务
            _LOGGER.warning("connection monitor: persistent_notification 更新失败(status=%s)", status)

    def stop(self) -> None:
        """Stop the service, called when component stops."""
        LogUtils.i(f"{LeelenService.__name__} stop")
        # 先标记停止再取消监控任务:stop() 在 unload(执行器线程)与 async_restart
        # 里都会走到,用 call_soon_threadsafe 在事件循环里取消;若 cancel 落地前
        # 任务恰好又醒一轮,凭 _monitor_stop 判定为「真正停止」发「已断开」并退出,
        # 而不是误判为启动初期继续空转。
        if self._monitor_task:
            self._monitor_stop = True
            self._hass.loop.call_soon_threadsafe(self._monitor_task.cancel)
            self._monitor_task = None
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