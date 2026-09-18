"""light 平台:无线灯(TYPE_WIRELESS_LIGHT)。"""
from __future__ import annotations


from homeassistant.components.light import LightEntity, ColorMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import POWER_ON, LIGHT_LOGIC_TYPES
from .entity_base import LeelenEntity
from .leelen.common.LeelenType import FunctionType, FunctionValue
from .leelen.models.ControlModel import ControlModel
from .leelen.states.LinBaseState import LinBaseState
from .leelen.utils.LogUtils import LogUtils
from .platform_helper import async_setup_entry as _setup_platform



def _build_entities(device_info, config_entry):
    """按 logic_type 建实体:TYPE_WIRELESS_LIGHT→Light。"""
    entities = []
    for logic_srv in device_info.get("logic_srv", []):
        if logic_srv.get("logic_type") in LIGHT_LOGIC_TYPES:
            entities.append(Light(
                logic_srv.get("logic_addr"),
                logic_srv.get("dev_addr"),
                logic_srv.get("logic_name"),
                device_info.get("dev_name"),
                config_entry))
    return entities


async def async_setup_entry(
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up a config entry."""
    await _setup_platform(hass, config_entry, async_add_entities, _build_entities)


class Light(LeelenEntity, LightEntity):
    """light 平台的无线灯实体。"""
    # name 属性返回完整名称,开启 _attr_has_entity_name 会导致名称被设备前缀重复
    _attr_color_mode = ColorMode.ONOFF
    _attr_supported_color_modes = {ColorMode.ONOFF}

    def __init__(self, logic_addr, device_id: str, name: str, dev_name: str, config_entry: ConfigEntry):
        super().__init__(logic_addr, device_id, name, dev_name, config_entry)
        self._attr_icon = 'mdi:lightbulb-group'

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the light on.

        Shall set attributes in kwargs if applicable.
        """
        ControlModel.get_instance().device_control(self._logic_addr, FunctionType.FUNCTION_ON_OFF,
                                                   FunctionValue.VALUE_ON)
        # 立即更新本地状态,否则 UI 直到下一次设备上报才反馈
        self._prop_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the light off."""
        ControlModel.get_instance().device_control(self._logic_addr, FunctionType.FUNCTION_ON_OFF,
                                                   FunctionValue.VALUE_OFF)
        self._prop_on = False
        self.async_write_ha_state()

    async def update_state(self, state: LinBaseState):
        LogUtils.d(f"💡 {self._name} update {state}")
        self._prop_on = state.power_state == POWER_ON
