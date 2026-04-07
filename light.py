# # -*- coding: utf-8 -*-
# """
#
# Light entities for Xiaomi Home.
# """
from __future__ import annotations

import logging
from typing import Any, Optional

from homeassistant.components.light import (
    LightEntity, ColorMode
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import LogUtils
from .const import DOMAIN
from .leelen.common.LeelenType import *
from .leelen.models.ControlModel import ControlModel
from .leelen.states.LinBaseState import LinBaseState

# from .miot.miot_spec import MIoTSpecProperty
# from .miot.miot_device import MIoTDevice, MIoTEntityData,  MIoTServiceEntity
# from .miot.const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def setup_devices_from_db(hass, config_entry, async_add_entities):
    device_list: list = hass.data[DOMAIN]['devices'].get(config_entry.entry_id) or []
    # 注册设备
    entities = []
    device_registry = dr.async_get(hass)
    for device_info in device_list:
        for logic_srv in device_info.get("logic_srv", []):
            if logic_srv.get("logic_type") in [LogicDeviceType.TYPE_WIRELESS_LIGHT]:
                entity = Light(logic_srv.get("logic_addr"),
                               logic_srv.get("dev_addr"),
                               logic_srv.get("logic_name"),
                               device_info.get("dev_name"),
                               config_entry)
                hass.data[DOMAIN]["entities"][entity.unique_id] = entity
                entities.append(entity)
    # 添加实体到 HA
    async_add_entities(entities)


async def async_setup_entry(
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up a config entry."""

    await setup_devices_from_db(hass, config_entry, async_add_entities)

    async def handle_refresh():
        await setup_devices_from_db(hass, config_entry, async_add_entities)

    async_dispatcher_connect(hass, "leelen_integration_device_refresh", handle_refresh)


class Light(LightEntity):
    """Light entities for Xiaomi Home."""
    # pylint: disable=unused-argument
    _VALUE_RANGE_MODE_COUNT_MAX = 30
    # _prop_on: Optional[MIoTSpecProperty]
    # _prop_brightness: Optional[MIoTSpecProperty]
    # _prop_color_temp: Optional[MIoTSpecProperty]
    # _prop_color: Optional[MIoTSpecProperty]
    # _prop_mode: Optional[MIoTSpecProperty]

    _brightness_scale: Optional[tuple[int, int]]
    _mode_map: Optional[dict[Any, Any]]
    _attr_has_entity_name = True  # 推荐启用以符合最新命名规范
    _attr_color_mode = ColorMode.ONOFF
    _attr_supported_color_modes = {ColorMode.ONOFF}

    def __init__(self, logic_addr, device_id: str, name: str,dev_name: str, config_entry: ConfigEntry):
        """Initialize the Light."""
        self._device_id = device_id
        self._name = name
        self._logic_addr = logic_addr
        self._device_name = dev_name
        self._prop_on = False  # 初始状态
        self._config_entry = config_entry
        self._attr_icon = 'mdi:lightbulb-group'

    @property
    def unique_id(self) -> str:
        return f"leelen_logic_addr_{self._logic_addr}"

    @property
    def name(self) -> str:
        return self._name

    @property
    def is_on(self) -> Optional[bool]:
        """Return if the light is on."""
        # value_on = self.get_prop_value(prop=self._prop_on)
        # # Dirty logic for lumi.gateway.mgl03 indicator light
        # if isinstance(value_on, int):
        #     value_on = value_on == 1
        return self._prop_on

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={("LEELEN_HOME", self._device_id)},
            name=self._device_name,
            manufacturer="LEELEN",
        )

    @property
    def brightness(self) -> Optional[int]:
        """Return the brightness."""
        return None
        # brightness_value = self.get_prop_value(prop=self._prop_brightness)
        # if brightness_value is None:
        #     return None
        # return value_to_brightness(self._brightness_scale, brightness_value)

    @property
    def color_temp_kelvin(self) -> Optional[int]:
        """Return the color temperature."""
        return None
        # return self.get_prop_value(prop=self._prop_color_temp)

    @property
    def rgb_color(self) -> Optional[tuple[int, int, int]]:
        """Return the rgb color value."""
        return None
        # rgb = self.get_prop_value(prop=self._prop_color)
        # if rgb is None:
        #     return None
        # r = (rgb >> 16) & 0xFF
        # g = (rgb >> 8) & 0xFF
        # b = rgb & 0xFF
        # return r, g, b

    @property
    def effect(self) -> Optional[str]:
        """Return the current mode."""
        return None
        # return self.get_map_value(
        #     map_=self._mode_map,
        #     key=self.get_prop_value(prop=self._prop_mode))

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

        # Dirty logic for lumi.gateway.mgl03 indicator light
        # value_on = False if self._prop_on.format_ == bool else 0
        # await self.set_property_async(prop=self._prop_on, value=value_on)

    async def update_state(self, state: LinBaseState):
        LogUtils.d(f"💡 {self._name} update {state}")
        self._prop_on = state.power_state == 1
