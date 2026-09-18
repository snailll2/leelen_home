"""switch 平台:智能插座(Switch)与 V设备(VSwitch,支持实体联动)。"""
from __future__ import annotations

import time
import logging
from typing import Callable, Optional

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event

from .const import (OPTIONS_CONFIG, OPTIONS_LINKED_ENTITIES, ARM_ON_PAYLOAD, ARM_OFF_PAYLOAD,
                    LINKED_ON_STATES, VSWITCH_STATE_ON, VSWITCH_STATE_OFF, SOCKET_LOGIC_TYPES)
from .entity_base import LeelenEntity
from .leelen.common.LeelenType import FunctionType, FunctionValue, LogicDeviceType
from .leelen.models.ControlModel import ControlModel
from .leelen.states.LinBaseState import LinBaseState
from .leelen.utils.LogUtils import LogUtils
from .platform_helper import async_setup_entry as _setup_platform

_LOGGER = logging.getLogger(__name__)

# 联动状态变化后,短时间内忽略设备上报驱动的回程同步(防回环),秒。
_LINKED_SYNC_DEBOUNCE = 2.0


def _build_entities(device_info, config_entry):
    """按 logic_type 建实体:智能插座→Switch,V设备→VSwitch(绑定联动实体)。"""
    entities = []
    # 老版本曾把 options 存在 data 里,读取时保留 data 兜底。
    options = config_entry.options.get(OPTIONS_CONFIG, config_entry.data.get(OPTIONS_CONFIG, {}))
    linked_entities = options.get(OPTIONS_LINKED_ENTITIES, {})
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
        self._power_usage = 0.0

    @property
    def extra_state_attributes(self):
        """Return entity specific state attributes."""
        return {
            "power_usage": round(self._power_usage, 2)
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
        if state.get_service_type() == FunctionType.FUNCTION_ON_OFF:
            self._prop_on = state.power_state == 1
        if state.get_service_type() == FunctionType.FUNCTION_POWER:
            self._power_usage = state.get_power()

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
