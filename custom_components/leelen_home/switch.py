"""switch 平台:智能插座(Switch)与 V设备(VSwitch,支持实体联动)。"""
from __future__ import annotations

import time
from typing import Callable, Optional

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event

from .const import (OPTIONS_CONFIG, OPTIONS_LINKED_ENTITIES, ARM_ON_PAYLOAD, ARM_OFF_PAYLOAD,
                    LINKED_ON_STATES, VSWITCH_STATE_ON, VSWITCH_STATE_OFF, SOCKET_LOGIC_TYPES)
from .entity_base import LeelenEntity
from .leelen.common.LeelenType import APCIType, FunctionType, FunctionValue, LogicDeviceType, PropertyId
from .leelen.models.ControlModel import ControlModel
from .leelen.states.LinBaseState import LinBaseState
from .leelen.utils.LogUtils import LogUtils
from .platform_helper import async_setup_entry as _setup_platform


# 联动状态变化后,短时间内忽略设备上报驱动的回程同步(防回环),秒。
_LINKED_SYNC_DEBOUNCE = 2.0

#: 面板指示灯实体 unique_id 前缀。属性 136(LIGHT_PATTERN)挂在面板设备自身
#: (dev_addr != 0),不经过任何 logic_srv 通道 —— 实体按「设备持有可写 136 属性」
#: 建出,故 id 直接带设备地址,不进「同步设备」清理白名单会被误删。
PANEL_LIGHT_UNIQUE_ID_PREFIX = "leelen_panel_light"


def _has_writable_panel_light(device_info) -> bool:
    """设备是否有可写的面板指示灯属性 136(LIGHT_PATTERN)。

    按协议定义匹配:属性存在(read_only == 0)即视为该面板支持指示灯控制,
    不写死任何设备名/地址。网关(dev_addr==0)由 sensor 平台建属性实体,排除。
    """
    if str(device_info.get("dev_addr")) == "0":
        return False
    return any(
        row.get("property_id") == PropertyId.LIGHT_PATTERN and row.get("read_only") == 0
        for row in device_info.get("all_property", [])
    )


def _panel_light_initial_on(val) -> bool:
    """属性 136 现值 → 初始开关态。LIGHT_PATTERN 语义推断自官方 App:01=开,00=关。

    dump.db 实测各面板默认 01(开);val 以 bytes(1 字节)存储。防御:空/None 按开
    处理(与出厂默认一致),未知字节按 >0 判开。
    """
    if val is None:
        return True
    if isinstance(val, (bytes, bytearray)):
        return not val or val[0] != 0
    if isinstance(val, str) and val.isdigit():
        return int(val) != 0
    return True


def _build_entities(device_info, config_entry):
    """按 logic_type 建实体:智能插座→Switch,V设备→VSwitch(绑定联动实体);
    面板指示灯→PanelIndicatorSwitch(属性 136 LIGHT_PATTERN 挂设备自身)。"""
    entities = []
    # 老版本曾把 options 存在 data 里,读取时保留 data 兜底。
    options = config_entry.options.get(OPTIONS_CONFIG, config_entry.data.get(OPTIONS_CONFIG, {}))
    linked_entities = options.get(OPTIONS_LINKED_ENTITIES, {})
    # 设备级面板指示灯开关:与逻辑通道无关,一台面板一个开关。
    # 初值取设备库属性 136 现值(all_property 由 query_devices 展开),
    # LIGHT_PATTERN 为写私有属性(WRITE_PRIVATE_PROPERTY=0x64),载荷 [pid][val]。
    if _has_writable_panel_light(device_info):
        initial_val = None
        for row in device_info.get("all_property", []):
            if row.get("property_id") == PropertyId.LIGHT_PATTERN:
                initial_val = row.get("val")
                break
        entities.append(PanelIndicatorSwitch(
            device_info.get("dev_addr"),
            device_info.get("dev_name"),
            config_entry,
            _panel_light_initial_on(initial_val)))
    for logic_srv in device_info.get("logic_srv", []):
        # 572(WIRELESS_DOUBLE_CURTAIN_PANEL):旧代码以裸数字当作插座位匹配。
        # dump.db 实测它挂在双路窗帘面板下且 srv_type=0,会被设备查询过滤,不会真正建实体。
        if logic_srv.get("logic_type") in SOCKET_LOGIC_TYPES:
            entities.append(Switch(
                logic_srv.get("logic_addr"),
                logic_srv.get("dev_addr"),
                logic_srv.get("logic_name"),
                device_info.get("dev_name"),
                config_entry))
        if logic_srv.get("logic_type") == LogicDeviceType.ARM:
            entity = VSwitch(
                logic_srv.get("logic_addr"),
                logic_srv.get("dev_addr"),
                logic_srv.get("logic_name"),
                device_info.get("dev_name"),
                config_entry)
            LogUtils.d(f"vswitch entity: {entity} {entity.unique_id} {linked_entities}")
            if entity.unique_id in linked_entities:
                entity.set_linked_entity(linked_entities[entity.unique_id])
            entities.append(entity)
    return entities


def _finalize_vswitch(entities, hass):
    """实体添加后(初始与 refresh 各批)注册联动实体的状态监听。"""
    for entity in entities:
        if isinstance(entity, VSwitch) and entity.get_linked_entity():
            entity.register_state_listener()


async def async_setup_entry(
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up a config entry."""
    await _setup_platform(hass, config_entry, async_add_entities, _build_entities, finalize=_finalize_vswitch)


class Switch(LeelenEntity, SwitchEntity):
    """switch 平台的智能插座实体。"""
    # pylint: disable=unused-argument
    _attr_has_entity_name = True  # 推荐启用以符合最新命名规范

    def __init__(self, logic_addr, device_id: str, name: str, dev_name: str, config_entry: ConfigEntry):
        super().__init__(logic_addr, device_id, name, dev_name, config_entry)
        # 用电统计按 HA Switch 标准属性暴露(数据源是网关电能表实时 fetch):
        # current_power_w = 20517 × 0.1(官方 App 口径);
        # today_energy_kwh / month_energy_kwh = 22556/22557 由 MsgStorageModel 计算。
        self._power_w = 0.0
        self._today_energy_kwh = 0.0
        self._month_energy_kwh = 0.0

    @property
    def extra_state_attributes(self):
        """Return entity specific state attributes."""
        return {
            "current_power_w": round(self._power_w, 1),
            "today_energy_kwh": round(self._today_energy_kwh, 3),
            "month_energy_kwh": round(self._month_energy_kwh, 1),
        }

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the switch on."""
        ControlModel.get_instance().device_control(self._logic_addr, FunctionType.FUNCTION_ON_OFF,
                                                   FunctionValue.VALUE_ON)
        self._prop_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the switch off."""
        ControlModel.get_instance().device_control(self._logic_addr, FunctionType.FUNCTION_ON_OFF,
                                                   FunctionValue.VALUE_OFF)
        self._prop_on = False
        self.async_write_ha_state()

    async def update_state(self, state: LinBaseState):
        LogUtils.d(f"💡 {self._name} update {state}")
        service_type = state.get_service_type()
        if service_type == FunctionType.FUNCTION_ON_OFF:
            self._prop_on = state.power_state == 1
        elif service_type == FunctionType.FUNCTION_POWER:
            # 功率上报(20517)原始值 × 0.1 → 瓦特(官方 App 口径)
            self._power_w = (state.get_power() or 0) * 0.1
        elif service_type == FunctionType.FUNCTION_SMART_SOCKET_HOUR_POWER:
            # 今日用电:22556(小时)由 AckToDao 从电能表合并,MsgStorageModel 已算好 kWh
            self._today_energy_kwh = state.get_power() or 0.0
        elif service_type == FunctionType.FUNCTION_SMART_SOCKET_DAY_POWER:
            # 本月用电:22557(日)同理
            self._month_energy_kwh = state.get_power() or 0.0

        self.async_write_ha_state()


class PanelIndicatorSwitch(LeelenEntity, SwitchEntity):
    """面板指示灯开关:控制面板设备自身的灯光指示(LIGHT_PATTERN 属性)。

    属性 136 挂在**设备自身**(dev_addr != 0),不经过任何逻辑通道 —— 所以
    ``_logic_addr=None`` 且不订阅状态事件,开关态按乐观更新维护;初值取自设备库
    属性现值。控制帧经 ``ControlModel.device_control`` 走真实登录连接,
    负载 = [136][val]:01 开 / 00 关。
    """

    # 归入设备「配置」分组,不占主控制区 —— 面板指示灯是纯设置项。
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, device_id, dev_name: str, config_entry: ConfigEntry,
                 initial_on: bool = True):
        # unique_id 用设备地址前缀,不能与 leelen_logic_addr_* 冲突。
        super().__init__(None, device_id, dev_name, dev_name, config_entry)
        self._prop_on = initial_on

    @property
    def unique_id(self) -> str:
        return f"{PANEL_LIGHT_UNIQUE_ID_PREFIX}_{self._device_id}"

    @property
    def name(self) -> str:
        return f"{self._device_name} 指示灯"

    @property
    def icon(self) -> str:
        return "mdi:led-on" if self._prop_on else "mdi:led-off"

    def _send(self, val: int) -> None:
        # 私有属性写:TlvUtils 对 control_type=0x64(100)编码为 d2 57 88 xx,
        # body = 07 4000 04 d2 57 88 xx(见 test_panel_light 写帧字节断言)。
        ControlModel.get_instance().device_control(
            self._device_id, APCIType.WRITE_PRIVATE_PROPERTY[0],
            bytes([PropertyId.LIGHT_PATTERN, val]))

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the panel indicator light on."""
        self._send(1)
        self._prop_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the panel indicator light off."""
        self._send(0)
        self._prop_on = False
        self.async_write_ha_state()


class VSwitch(Switch):
    """V设备:布防型开关,可关联一个 HA 实体做双向状态同步。"""

    def __init__(self, logic_addr, device_id: str, name: str, dev_name: str, config_entry: ConfigEntry):
        super().__init__(logic_addr, device_id, name, dev_name, config_entry)
        self._linked_entity_id: Optional[str] = None
        self._is_syncing = False
        # 注意:联动监听的退订句柄不能复用父类 StateUpdateSubscriber 的
        # _state_unsub —— 两者生命周期不同,复用会互相覆盖导致订阅泄漏。
        self._linked_state_unsub: Optional[Callable] = None
        self._last_sync_time = 0.0

    def set_linked_entity(self, entity_id: str) -> None:
        self._linked_entity_id = entity_id

    def get_linked_entity(self) -> Optional[str]:
        return self._linked_entity_id

    async def _sync_linked_entity_state(self, target_state: bool) -> None:
        if not self._linked_entity_id or self._is_syncing:
            return
        LogUtils.d(f"💡 {self._name} sync linked entity {self._linked_entity_id} state to {target_state}")

        self._is_syncing = True
        try:
            state = self.hass.states.get(self._linked_entity_id)
            on_state = "on" if target_state else "off"
            if state and state.state != on_state:
                await self.hass.services.async_call(
                    "homeassistant",
                    "turn_on" if target_state else "turn_off",
                    {"entity_id": self._linked_entity_id},
                    blocking=False
                )
            self._last_sync_time = time.monotonic()
        finally:
            self._is_syncing = False

    async def _linked_entity_state_changed(self, event: Event) -> None:
        """联动实体状态变化 → 反向驱动 V设备布防/撤防。"""
        if self._is_syncing:
            return
        to_state = event.data.get("new_state")
        entity_id = event.data.get("entity_id")
        if not to_state:
            return
        LogUtils.d(f"💡 {self._name} linked entity state changed {entity_id} to {to_state.state}")

        if entity_id != self._linked_entity_id:
            return
        if time.monotonic() - self._last_sync_time < _LINKED_SYNC_DEBOUNCE:
            LogUtils.d(f"💡 {self._name} ignoring linked entity change (just synced)")
            return
        new_state = to_state.state in LINKED_ON_STATES
        if new_state == self._prop_on:
            return
        self._is_syncing = True
        try:
            if new_state:
                ControlModel.get_instance().device_control(
                    self._logic_addr, FunctionType.FUNCTION_ARM, ARM_ON_PAYLOAD)
                self._prop_on = True
            else:
                ControlModel.get_instance().device_control(
                    self._logic_addr, FunctionType.FUNCTION_ARM_CONDITION, ARM_OFF_PAYLOAD)
                self._prop_on = False
            self.async_write_ha_state()
        finally:
            self._is_syncing = False

    def register_state_listener(self) -> None:
        if self._linked_entity_id and not self._linked_state_unsub:
            self._linked_state_unsub = async_track_state_change_event(
                self.hass,
                self._linked_entity_id,
                self._linked_entity_state_changed
            )

    def unregister_state_listener(self) -> None:
        if self._linked_state_unsub:
            self._linked_state_unsub()
            self._linked_state_unsub = None

    async def async_will_remove_from_hass(self) -> None:
        """卸载时同步注销联动监听(否则 reload 后残留旧监听指向已移除实体)。"""
        self.unregister_state_listener()
        await super().async_will_remove_from_hass()

    @property
    def extra_state_attributes(self):
        """Return entity specific state attributes."""
        attrs = super().extra_state_attributes
        # V设备没有功率/用电概念(update_state 也不消费电能事件),剔除 Switch 的
        # 电参数属性,避免布防开关一直顶着 current_power_w:0.0 之类误导。
        for key in ("current_power_w", "today_energy_kwh", "month_energy_kwh"):
            attrs.pop(key, None)
        if self._linked_entity_id:
            attrs["linked_entity"] = self._linked_entity_id
        return attrs

    async def async_turn_on(self, **kwargs) -> None:
        ControlModel.get_instance().device_control(
            self._logic_addr, FunctionType.FUNCTION_ARM, ARM_ON_PAYLOAD)
        self._prop_on = True
        self.async_write_ha_state()
        await self._sync_linked_entity_state(True)

    async def async_turn_off(self, **kwargs) -> None:
        ControlModel.get_instance().device_control(
            self._logic_addr, FunctionType.FUNCTION_ARM_CONDITION, ARM_OFF_PAYLOAD)
        self._prop_on = False
        self.async_write_ha_state()
        await self._sync_linked_entity_state(False)

    async def update_state(self, state: LinBaseState):
        if self._is_syncing:
            LogUtils.d(f"💡 {self._name} update skipped during sync")
            return
        LogUtils.d(f"💡 {self._name} update {state}")
        if state.get_service_type() in [
            FunctionType.FUNCTION_ARM,
            FunctionType.FUNCTION_ARM_CONDITION
        ]:
            # ARM(开启)/ARM_CONDITION(关闭) 是设备上报的可解析状态来源;
            # 原实现只在有 linked_entity 时才更新,导致无联动时 VSwitch 状态永不刷新。
            # 以设备上报为准(1=布防开, 2=撤防关,见 get_v_switch_state)。
            if state.power_state in (VSWITCH_STATE_ON, VSWITCH_STATE_OFF):
                self._prop_on = state.power_state == VSWITCH_STATE_ON

            # 有 linked entity 时,以其当前状态为准覆盖设备上报(保留原覆盖逻辑)
            if self._linked_entity_id:
                linked_state = self.hass.states.get(self._linked_entity_id)
                if linked_state is not None:
                    self._prop_on = linked_state.state in LINKED_ON_STATES

        self.async_write_ha_state()
        await self._sync_linked_entity_state(self._prop_on)
