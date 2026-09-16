"""HA 原生状态事件派发入口(原自定义事件总线)。

原 FlowRxBus 是一个持有 ``hass`` 单例事件总线,reload 后残留问题明显。
已重构为无状态模块:后台线程(收包线程)调用 ``post(event)`` 把设备状态事件
经 ``hass.loop.call_soon_threadsafe`` 送入 HA 原生 ``async_dispatcher_send``。

实体侧的订阅由各平台混入的 ``StateUpdateSubscriber`` 完成(见 state_subscription.py),
本模块不再保存单例或 hass,事件总线不再有全局状态。
"""

from ..HeartbeatService import HeartbeatService
from ...state_subscription import post_state_update

#: 保留旧名称,供心跳/收包线程按原逻辑调用;内部委托给 HA dispatcher。
def post(event) -> None:
    hass = HeartbeatService.get_instance().hass
    post_state_update(hass, event)