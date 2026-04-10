"""Light entities for Leelen Home."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.light import LightEntity, ColorMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .leelen.common.LeelenType import FunctionType, FunctionValue, LogicDeviceType
from .leelen.models.ControlModel import ControlModel
from .leelen.states.LinBaseState import LinBaseState
from .leelen.utils.LogUtils import LogUtils

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up light entities."""
    entities = await _create_entities(hass, config_entry)
    async_add_entities(entities)

    async def handle_refresh():
        new_entities = await _create_entities(hass, config_entry)
        async_add_entities(new_entities)

    async_dispatcher_connect(hass, "leelen_integration_device_refresh", handle_refresh)


async def _create_entities(hass: HomeAssistant, config_entry: ConfigEntry) -> list[Light]:
    """Create light entities from device data."""
    device_list: list = hass.data[DOMAIN]["devices"].get(config_entry.entry_id, [])
    entities = []

    for device_info in device_list:
        for logic_srv in device_info.get("logic_srv", []):
            if logic_srv.get("logic_type") == LogicDeviceType.TYPE_WIRELESS_LIGHT:
                entity = Light(
                    logic_srv.get("logic_addr"),
                    logic_srv.get("dev_addr"),
                    logic_srv.get("logic_name"),
                    device_info.get("dev_name"),
                    config_entry,
                )
                hass.data[DOMAIN]["entities"][entity.unique_id] = entity
                entities.append(entity)

    return entities


class Light(LightEntity):
    """Light entity for Leelen Home."""

    _attr_has_entity_name = True
    _attr_color_mode = ColorMode.ONOFF
    _attr_supported_color_modes = {ColorMode.ONOFF}

    def __init__(
        self,
        logic_addr: int,
        device_id: str,
        name: str,
        dev_name: str,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the light."""
        self._device_id = device_id
        self._name = name
        self._logic_addr = logic_addr
        self._device_name = dev_name
        self._prop_on = False
        self._config_entry = config_entry
        self._attr_icon = "mdi:lightbulb-group"

    @property
    def unique_id(self) -> str:
        return f"leelen_logic_addr_{self._logic_addr}"

    @property
    def name(self) -> str:
        return self._name

    @property
    def is_on(self) -> bool:
        """Return if the light is on."""
        return self._prop_on

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={("LEELEN_HOME", self._device_id)},
            name=self._device_name,
            manufacturer="LEELEN",
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on."""
        ControlModel.get_instance().device_control(
            self._logic_addr, FunctionType.FUNCTION_ON_OFF, FunctionValue.VALUE_ON
        )
        self._prop_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light off."""
        ControlModel.get_instance().device_control(
            self._logic_addr, FunctionType.FUNCTION_ON_OFF, FunctionValue.VALUE_OFF
        )
        self._prop_on = False
        self.async_write_ha_state()

    async def update_state(self, state: LinBaseState) -> None:
        """Update state from device."""
        LogUtils.d(__name__, f"Light {self._name} update: {state}")
        self._prop_on = state.power_state == 1
        self.async_write_ha_state()
