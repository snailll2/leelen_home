"""Switch entities for Leelen Home."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
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
    """Set up switch entities."""
    entities = await _create_entities(hass, config_entry)
    async_add_entities(entities)

    async def handle_refresh():
        new_entities = await _create_entities(hass, config_entry)
        async_add_entities(new_entities)

    async_dispatcher_connect(hass, "leelen_integration_device_refresh", handle_refresh)


async def _create_entities(hass: HomeAssistant, config_entry: ConfigEntry) -> list[Switch]:
    """Create switch entities from device data."""
    device_list: list = hass.data[DOMAIN]["devices"].get(config_entry.entry_id, [])
    entities = []

    for device_info in device_list:
        for logic_srv in device_info.get("logic_srv", []):
            if logic_srv.get("logic_type") in [LogicDeviceType.ZIGBEE_SMART_WALL_SOCKET, 572]:
                entity = Switch(
                    logic_srv.get("logic_addr"),
                    logic_srv.get("dev_addr"),
                    logic_srv.get("logic_name"),
                    device_info.get("dev_name"),
                    config_entry,
                )
                hass.data[DOMAIN]["entities"][entity.unique_id] = entity
                entities.append(entity)

    return entities


class Switch(SwitchEntity):
    """Switch entity for Leelen Home."""

    _attr_has_entity_name = True

    def __init__(
        self,
        logic_addr: int,
        device_id: str,
        name: str,
        dev_name: str,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the switch."""
        self._device_id = device_id
        self._name = name
        self._logic_addr = logic_addr
        self._device_name = dev_name
        self._config_entry = config_entry
        self._prop_on = False
        self._power_usage = 0.0

    @property
    def unique_id(self) -> str:
        return f"leelen_logic_addr_{self._logic_addr}"

    @property
    def name(self) -> str:
        return self._name

    @property
    def is_on(self) -> bool:
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
    def extra_state_attributes(self) -> dict[str, float]:
        """Return entity specific state attributes."""
        return {"power_usage": round(self._power_usage, 2)}

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        ControlModel.get_instance().device_control(
            self._logic_addr, FunctionType.FUNCTION_ON_OFF, FunctionValue.VALUE_ON
        )
        self._prop_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        ControlModel.get_instance().device_control(
            self._logic_addr, FunctionType.FUNCTION_ON_OFF, FunctionValue.VALUE_OFF
        )
        self._prop_on = False
        self.async_write_ha_state()

    async def update_state(self, state: LinBaseState) -> None:
        """Update state from device."""
        LogUtils.d(__name__, f"Switch {self._name} update: {state}")
        if state.get_service_type() == FunctionType.FUNCTION_ON_OFF:
            self._prop_on = state.power_state == 1
        if state.get_service_type() == FunctionType.FUNCTION_POWER:
            self._power_usage = state.get_power()
        self.async_write_ha_state()
