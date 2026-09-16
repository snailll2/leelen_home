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

    def subscribe_state_updates(self, hass) -> None:
        self._state_unsub = async_dispatcher_connect(
            hass, SIGNAL_STATE_UPDATE, self._handle_state_event
        )

    async def async_will_remove_from_hass(self) -> None:
        """注销订阅,避免 reload/重加实体后残留重复回调。"""
        if self._state_unsub:
            self._state_unsub()
            self._state_unsub = None
        sup = getattr(super(), "async_will_remove_from_hass", None)
        if sup is not None:
            await sup()

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