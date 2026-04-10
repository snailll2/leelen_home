# -*- coding: utf-8 -*-

from __future__ import annotations

import logging
from typing import Any, Optional

from homeassistant.components.sensor import SensorEntity
from homeassistant.components.binary_sensor import BinarySensorEntity

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
# from homeassistant.const import TEMP_CELSIUS

from . import LogUtils
from .const import DOMAIN
from .leelen.common.LeelenType import *
from .leelen.states.LinSensorState import LinSensorState

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
        # device_id, name, model = device_info
        # device_registry.async_get_or_create(
        #     config_entry_id=config_entry.entry_id,
        #     identifiers={("LEELEN_HOME", device_info.get("dev_addr"))},
        #     manufacturer="LEELEN",
        #     name=device_info.get("dev_name"),
        #     model=device_info.get("dev_type"),
        # )
        for logic_srv in device_info.get("logic_srv", []):

            if logic_srv.get("logic_type") in [LogicDeviceType.TYPE_TEMPERATURE_SENSOR]:
                entity = Sensor(logic_srv.get("logic_addr"),
                                logic_srv.get("dev_addr"),
                                logic_srv.get("logic_name"),
                                device_info.get("dev_name"),
                                "temperature",
                                "°C",
                                config_entry)
                hass.data[DOMAIN]["entities"][entity.unique_id] = entity
                entities.append(entity)

            if logic_srv.get("logic_type") in [LogicDeviceType.TYPE_PM_SENSOR]:
                entity = Sensor(logic_srv.get("logic_addr"),
                                logic_srv.get("dev_addr"),
                                logic_srv.get("logic_name"),
                                device_info.get("dev_name"),
                                "pm25",
                                "µg/m³",
                                config_entry)
                hass.data[DOMAIN]["entities"][entity.unique_id] = entity
                entities.append(entity)

            if logic_srv.get("logic_type") in [LogicDeviceType.TYPE_HUMIDITY_SENSOR]:
                entity = Sensor(logic_srv.get("logic_addr"),
                                logic_srv.get("dev_addr"),
                                logic_srv.get("logic_name"),
                                device_info.get("dev_name"),
                                "humidity",
                                "%",
                                config_entry)
                hass.data[DOMAIN]["entities"][entity.unique_id] = entity
                entities.append(entity)

            if logic_srv.get("logic_type") in [LogicDeviceType.TYPE_WIRELESS_DOOR_SENSOR]:
                entity = BinarySensor(logic_srv.get("logic_addr"),
                                logic_srv.get("dev_addr"),
                                logic_srv.get("logic_name"),
                                device_info.get("dev_name"),
                                "door",
                                config_entry)
                hass.data[DOMAIN]["entities"][entity.unique_id] = entity
                entities.append(entity)

            if logic_srv.get("logic_type") in [LogicDeviceType.TYPE_WIRELESS_WATER_IMMERSION_SENSOR]:
                entity = BinarySensor(logic_srv.get("logic_addr"),
                                logic_srv.get("dev_addr"),
                                logic_srv.get("logic_name"),
                                device_info.get("dev_name"),
                                "moisture",
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


class Sensor(SensorEntity):

    _attr_has_entity_name = True  # 推荐启用以符合最新命名规范

    def __init__(self, logic_addr, device_id: str, name: str, dev_name: str,device_class,unit_of_measurement, config_entry: ConfigEntry):
        """Initialize the Light."""
        self._device_id = device_id
        self._name = name
        self._logic_addr = logic_addr
        self._device_name = dev_name
        
        self._config_entry = config_entry
        self._attr_device_class = device_class
        self._attr_native_unit_of_measurement = unit_of_measurement

        self._prop_on = False  # 初始状态


    @property
    def unique_id(self) -> str:
        return f"leelen_logic_addr_{self._logic_addr}"

    @property
    def name(self) -> str:
        return self._name

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={("LEELEN_HOME", self._device_id)},
            name=self._device_name,
            manufacturer="LEELEN",
        )

    @property
    def native_value(self) -> Any:
        """Return the current value of the sensor."""
        return self._attr_native_value

    async def update_state(self, state: LinSensorState):
        LogUtils.d(f"update {state}")
        if isinstance(state, LinSensorState):
            self._attr_native_value = state.get_value()
        


class BinarySensor(BinarySensorEntity):

    _attr_has_entity_name = True  # 推荐启用以符合最新命名规范

    def __init__(self, logic_addr, device_id: str, name: str, dev_name: str,device_class, config_entry: ConfigEntry):
        """Initialize the Light."""
        self._device_id = device_id
        self._name = name
        self._logic_addr = logic_addr
        self._device_name = dev_name
        
        self._config_entry = config_entry
        self._attr_device_class = device_class
        
        self._prop_on = False  # 初始状态


    @property
    def unique_id(self) -> str:
        return f"leelen_logic_addr_{self._logic_addr}"

    @property
    def name(self) -> str:
        return self._name

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={("LEELEN_HOME", self._device_id)},
            name=self._device_name,
            manufacturer="LEELEN",
        )

    @property
    def is_on(self):
        return self._prop_on


    async def update_state(self, state: LinSensorState):
        # LogUtils.d(f"🧯 {self._name} update {state}")
        if isinstance(state, LinSensorState):
            self._prop_on = state.get_value() == 0


