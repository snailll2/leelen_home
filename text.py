# # -*- coding: utf-8 -*-
# """
#
# Light entities for Xiaomi Home.
# """
from __future__ import annotations

import logging
from typing import Optional

from homeassistant.components.text import TextEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .leelen.common import PropertyId

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
        for property in device_info.get("all_property", []):
            # if logic_srv.get("logic_type") in [LogicDeviceType.TYPE_WIRELESS_LIGHT]:
            # property_id = property.get("property_id")
            for property_name, property_id in PropertyId.__dict__.items():
                if property_id == property.get("property_id"):
                    entity = Text("property_" + property_name,
                                  device_info.get("dev_addr"),
                                  str(property.get("val")),
                                  config_entry)
                    hass.data[DOMAIN]["entities"][entity.unique_id] = entity
                    entities.append(entity)
        # 为每个设备创建 Light 实体
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


class Text(TextEntity):
    """Text entities for Xiaomi Home."""

    def __init__(self, name, device_id: str, value: str, config_entry: ConfigEntry):
        """Initialize the Light."""
        self._device_id = device_id
        self._name = name
        self._prop_on = False  # 初始状态
        self._config_entry = config_entry
        self._value = value

    @property
    def unique_id(self) -> str:
        return f"leelen_logic_addr_{self._name}"

    @property
    def name(self) -> str:
        return self._name

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={("LEELEN_HOME", self._device_id)},
            name=self._name,
            manufacturer="LEELEN",
        )

    @property
    def native_value(self) -> Optional[str]:
        """Return the current text value."""
        if isinstance(self._value, str):
            return self._value[:255]
        return self._value
