"""实体状态更新的 HA 原生派发。

将原 FlowRxBus 的「单例事件总线 + dict 按 unique_id 查找 + hass.add_job」
重构为 Home Assistant 原生 async_dispatcher_send / async_dispatcher_connect:

- 后台线程(LAN/WAN 收包 → AckToDao / LogicServerStateModel)调用 ``post_state_update``,
  通过 ``hass.loop.call_soon_threadsafe`` 把信号送到事件循环 —— 线程安全、行为不变。
- 各平台实体在 setup 时经 ``StateUpdateSubscriber.subscribe_state_updates`` 订阅,
  收到与自身 unique_id 匹配的事件后调用各自 ``update_state`` 并写回 HA 状态。

不再有藏在单例里的 hass,不再有 reload 残留。
"""

from homeassistant.helpers.dispatcher import async_dispatcher_connect, async_dispatcher_send

from .leelen.common.CommonModel import CommonModel

#: 全系统唯一的状态更新信号。携带 DeviceStatusEvent 对象。
SIGNAL_STATE_UPDATE = "leelen_state_update"

#: 网关链路(连接/登录)状态变化信号,由 service.py 的连接监控广播。
#: 实体收到后重写一次 HA 状态,使 ``available`` 的变化立刻反映到界面上
#: (可用性属性只有在写状态时才会被 HA 读取)。
SIGNAL_AVAILABILITY_UPDATE = "leelen_availability_update"


def gateway_link_up() -> bool:
    """网关链路当前是否已登录 —— 实体 ``available`` 的判据。

    与 service.py 连接监控同源:按当前连接模式看 connect_wan / connect_lan,
    未建立、登录中、登录失败、已断开一律视为不可用;WAN 模式下 connect_lan 恒为 None。
    """
    from .const import CONNECT_MODE_WAN
    from .leelen.HeartbeatService import HeartbeatService

    hs = HeartbeatService.get_instance()
    conn = hs.connect_wan if hs.request_mode == CONNECT_MODE_WAN else hs.connect_lan
    return conn is not None and conn.is_logged_on()


def post_state_update(hass, event) -> None:
    """后台线程入口:把 state 更新事件调度到 HA 事件循环的 dispatcher。

    ``async_dispatcher_send`` 必须在事件循环线程内调用,故经 ``call_soon_threadsafe``
    包装以兼容非循环线程调用。
    """
    if hass is None:
        return
    hass.loop.call_soon_threadsafe(
        lambda: async_dispatcher_send(hass, SIGNAL_STATE_UPDATE, event)
    )


class StateUpdateSubscriber:
    """供各平台实体混入的更新订阅器。

    用法(平台 setup):
        entity = MyEntity(...)
        entity.subscribe_state_updates(hass)
        entities.append(entity)
    实体收到匹配自身 unique_id 的 DeviceStatusEvent 后调用 ``self.update_state(state)``。
    """

    _state_unsub = None
    #: 链路可用性变化的退订句柄。与 _state_unsub 分开保存 —— 共用一个字段会让两次订阅
    #: 互相覆盖退订句柄,导致其中一个订阅泄漏(此类错误此前已在 VSwitch 上踩过)。
    _availability_unsub = None

    def subscribe_state_updates(self, hass) -> None:
        # 防御:同一实例二次订阅前先退掉旧的,避免残留回调导致事件重复派发。
        if self._state_unsub:
            self._state_unsub()
            self._state_unsub = None
        self._state_unsub = async_dispatcher_connect(
            hass, SIGNAL_STATE_UPDATE, self._handle_state_event
        )
        if self._availability_unsub:
            self._availability_unsub()
            self._availability_unsub = None
        # 链路可用性变化:只需重写状态,让 available 的新值生效。
        self._availability_unsub = async_dispatcher_connect(
            hass, SIGNAL_AVAILABILITY_UPDATE, self._handle_availability_event
        )

    async def async_will_remove_from_hass(self) -> None:
        """注销订阅,避免 reload/重加实体后残留重复回调。"""
        if self._state_unsub:
            self._state_unsub()
            self._state_unsub = None
        if self._availability_unsub:
            self._availability_unsub()
            self._availability_unsub = None
        sup = getattr(super(), "async_will_remove_from_hass", None)
        if sup is not None:
            await sup()

    async def _handle_availability_event(self) -> None:
        """链路状态变化 → 重写 HA 状态(HA 只在写状态时才读取 available)。

        必须是协程:dispatcher 对同步回调会在**调用方线程**里直接执行,而
        ``async_write_ha_state`` 要求跑在事件循环线程;写成协程后 HA 会把它调度到
        循环上执行,与 _handle_state_event 一致。
        """
        self.async_write_ha_state()

    async def _handle_state_event(self, event) -> None:
        """根据事件更新本实体状态(与旧 FlowRxBus.async_operation 语义一致)。"""
        expected_id = f"leelen_logic_addr_{event.logic_address}"
        if self.unique_id != expected_id:
            return
        state = CommonModel.get_instance().get_cur_state(
            event.logic_address, event.function_id, event.state
        )
        state.service_type = event.function_id
        state.service_address = event.logic_address
        await self.update_state(state)
        self.async_write_ha_state()