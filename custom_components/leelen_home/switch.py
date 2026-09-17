"""switch 平台:智能插座(Switch)与布防开关(VSwitch,支持实体联动)。"""
from __future__ import annotations
import time
import logging
from typing import Optional

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change

from . import LogUtils
from .const import DOMAIN, OPTIONS_CONFIG, OPTIONS_LINKED_ENTITIES
from .leelen.common.LeelenType import FunctionType, FunctionValue, LogicDeviceType
from .leelen.models.ControlModel import ControlModel
from .leelen.states.LinBaseState import LinBaseState
from .platform_helper import async_setup_entry as _setup_platform
from .state_subscription import StateUpdateSubscriber

_LOGGER = logging.getLogger(__name__)


def _build_entities(device_info, config_entry):
    """按 logic_type 建实体:智能插座→Switch,布防→VSwitch(绑定联动实体)。"""
    entities = []
    linked_entities = config_entry.options.get(OPTIONS_CONFIG, config_entry.data.get(OPTIONS_CONFIG, {})).get(OPTIONS_LINKED_ENTITIES, {})
    LogUtils.d(f"switch linked_entities: {linked_entities}")
    for logic_srv in device_info.get("logic_srv", []):
        if logic_srv.get("logic_type") in [LogicDeviceType.ZIGBEE_SMART_WALL_SOCKET, 572]:
            entities.append(Switch(
                logic_srv.get("logic_addr"),
                logic_srv.get("dev_addr"),
                logic_srv.get("logic_name"),
                device_info.get("dev_name"),
                config_entry))
        if logic_srv.get("logic_type") in [LogicDeviceType.ARM]:
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


class Switch(StateUpdateSubscriber, SwitchEntity):
    """switch 平台的智能插座实体。"""
    # pylint: disable=unused-argument
    _attr_has_entity_name = True  # 推荐启用以符合最新命名规范

    def __init__(self, logic_addr, device_id: str, name: str,dev_name: str, config_entry: ConfigEntry):
        """Initialize the Light."""
        self._device_id = device_id
        self._name = name
        self._logic_addr = logic_addr
        self._device_name = dev_name
        self._prop_on = False  # 初始状态
        self._config_entry = config_entry
        self._power_usage = 0.0

    @property
    def unique_id(self) -> str:
        return f"leelen_logic_addr_{self._logic_addr}"

    @property
    def name(self) -> str:
        return self._name

    @property
    def is_on(self) -> Optional[bool]:
        """Return if the switch is on."""
        return self._prop_on

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={("LEELEN_HOME", self._device_id)},
            name=self._device_name,
            manufacturer="LEELEN",
        )
    @property
    def extra_state_attributes(self):
        """Return entity specific state attributes."""
        return {
            "power_usage": round(self._power_usage, 2)
        }


    async def async_turn_on(self, **kwargs) -> None:
        """Turn the light on.

        Shall set attributes in kwargs if applicable.
        """
        ControlModel.get_instance().device_control(self._logic_addr, FunctionType.FUNCTION_ON_OFF,
                                                   FunctionValue.VALUE_ON)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the light off."""
        # if not self._prop_on:
        #     return
        ControlModel.get_instance().device_control(self._logic_addr, FunctionType.FUNCTION_ON_OFF,
                                                   FunctionValue.VALUE_OFF)
        self.async_write_ha_state()

    async def update_state(self, state: LinBaseState):
        LogUtils.d(f"💡 {self._name} update {state}")
        if state.get_service_type() == FunctionType.FUNCTION_ON_OFF:
            self._prop_on = state.power_state == 1
        if state.get_service_type() == FunctionType.FUNCTION_POWER:
            self._power_usage = state.get_power()
        
        self.async_write_ha_state()



class VSwitch(Switch):
    _linked_entity_id: Optional[str] = None
    _is_syncing: bool = False
    _state_unsub: Optional[callable] = None
    _last_sync_time: float = 0.0

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
            if state and state.state != ("on" if target_state else "off"):
                await self.hass.services.async_call(
                    "homeassistant",
                    "turn_on" if target_state else "turn_off",
                    {"entity_id": self._linked_entity_id},
                    blocking=False
                )
            self._last_sync_time = time.monotonic()
        finally:
            self._is_syncing = False

    async def _linked_entity_state_changed(self, entity_id: str, from_state: State, to_state: State) -> None:
        if self._is_syncing or not to_state:
            return
        LogUtils.d(f"💡 {self._name} linked entity state changed {entity_id} from {from_state} to {to_state}")

        if entity_id != self._linked_entity_id:
            return
        if time.monotonic() - self._last_sync_time < 2.0:
            LogUtils.d(f"💡 {self._name} ignoring linked entity change (just synced)")
            return
        new_state = to_state.state in ("on", "open", "locked")
        if new_state == self._prop_on:
            return
        self._is_syncing = True
        try:
            if new_state:
                ControlModel.get_instance().device_control(self._logic_addr, FunctionType.FUNCTION_ARM,
                                                           bytes([1,0,0,0 ]))
                self._prop_on = True
            else:
                ControlModel.get_instance().device_control(self._logic_addr, FunctionType.FUNCTION_ARM_CONDITION,
                                                           bytes([2,0,0,0 ]))
                self._prop_on = False
            self.async_write_ha_state()
        finally:
            self._is_syncing = False

    def register_state_listener(self) -> None:
        if self._linked_entity_id and not self._state_unsub:
            self._state_unsub = async_track_state_change(
                self.hass,
                self._linked_entity_id,
                self._linked_entity_state_changed
            )

    def unregister_state_listener(self) -> None:
        if self._state_unsub:
            self._state_unsub()
            self._state_unsub = None

    @property
    def extra_state_attributes(self):
        """Return entity specific state attributes."""
        attrs = super().extra_state_attributes
        if self._linked_entity_id:
            attrs["linked_entity"] = self._linked_entity_id
        return attrs

    async def async_turn_on(self, **kwargs) -> None:
        ControlModel.get_instance().device_control(self._logic_addr, FunctionType.FUNCTION_ARM ,
                                                   bytes([1,0,0,0 ]))
        self._prop_on = True
        self.async_write_ha_state()
        await self._sync_linked_entity_state(True)

    async def async_turn_off(self, **kwargs) -> None:
        ControlModel.get_instance().device_control(self._logic_addr, FunctionType.FUNCTION_ARM_CONDITION ,
                                                   bytes([2,0,0,0 ]))
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
            # 现在以设备上报为准(power_state 1=开,2=关,见 get_v_switch_state)。
            if state.power_state in (1, 2):
                self._prop_on = state.power_state == 1

            # 有 linked entity 时,以其当前状态为准覆盖设备上报(保留原覆盖逻辑)
            if self._linked_entity_id:
                linked_state = self.hass.states.get(self._linked_entity_id)
                if linked_state is not None:
                    self._prop_on = linked_state.state == "on"

        self.async_write_ha_state()
        await self._sync_linked_entity_state(self._prop_on)
