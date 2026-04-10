"""Sensor entities for Leelen Home."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .leelen.common.LeelenType import LogicDeviceType
from .leelen.states.LinSensorState import LinSensorState
from .leelen.utils.LogUtils import LogUtils

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensor entities."""
    entities = await _create_entities(hass, config_entry)
    async_add_entities(entities)

    async def handle_refresh():
        new_entities = await _create_entities(hass, config_entry)
        async_add_entities(new_entities)

    async_dispatcher_connect(hass, "leelen_integration_device_refresh", handle_refresh)


async def _create_entities(hass: HomeAssistant, config_entry: ConfigEntry) -> list[SensorEntity]:
    """Create sensor entities from device data."""
    device_list: list = hass.data[DOMAIN]["devices"].get(config_entry.entry_id, [])
    entities: list[SensorEntity] = []

    for device_info in device_list:
        for logic_srv in device_info.get("logic_srv", []):
            logic_type = logic_srv.get("logic_type")
            addr = logic_srv.get("logic_addr")
            dev_addr = logic_srv.get("dev_addr")
            name = logic_srv.get("logic_name")
            dev_name = device_info.get("dev_name")

            if logic_type == LogicDeviceType.TYPE_TEMPERATURE_SENSOR:
                entity = Sensor(addr, dev_addr, name, dev_name, "temperature", "°C", config_entry)
                hass.data[DOMAIN]["entities"][entity.unique_id] = entity
                entities.append(entity)
            elif logic_type == LogicDeviceType.TYPE_PM_SENSOR:
                entity = Sensor(addr, dev_addr, name, dev_name, "pm25", "µg/m³", config_entry)
                hass.data[DOMAIN]["entities"][entity.unique_id] = entity
                entities.append(entity)
            elif logic_type == LogicDeviceType.TYPE_HUMIDITY_SENSOR:
                entity = Sensor(addr, dev_addr, name, dev_name, "humidity", "%", config_entry)
                hass.data[DOMAIN]["entities"][entity.unique_id] = entity
                entities.append(entity)
            elif logic_type == LogicDeviceType.TYPE_WIRELESS_DOOR_SENSOR:
                entity = BinarySensor(addr, dev_addr, name, dev_name, "door", config_entry)
                hass.data[DOMAIN]["entities"][entity.unique_id] = entity
                entities.append(entity)
            elif logic_type == LogicDeviceType.TYPE_WIRELESS_WATER_IMMERSION_SENSOR:
                entity = BinarySensor(addr, dev_addr, name, dev_name, "moisture", config_entry)
                hass.data[DOMAIN]["entities"][entity.unique_id] = entity
                entities.append(entity)

    return entities


class Sensor(SensorEntity):
    """Sensor entity for Leelen Home."""

    _attr_has_entity_name = True

    def __init__(
        self,
        logic_addr: int,
        device_id: str,
        name: str,
        dev_name: str,
        device_class: str,
        unit_of_measurement: str,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        self._device_id = device_id
        self._name = name
        self._logic_addr = logic_addr
        self._device_name = dev_name
        self._config_entry = config_entry
        self._attr_device_class = device_class
        self._attr_native_unit_of_measurement = unit_of_measurement

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

    async def update_state(self, state: LinSensorState) -> None:
        """Update state from device."""
        LogUtils.d(__name__, f"Sensor {self._name} update: {state}")
        if isinstance(state, LinSensorState):
            self._attr_native_value = state.get_value()


class BinarySensor(BinarySensorEntity):
    """Binary sensor entity for Leelen Home."""

    _attr_has_entity_name = True

    def __init__(
        self,
        logic_addr: int,
        device_id: str,
        name: str,
        dev_name: str,
        device_class: str,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the binary sensor."""
        self._device_id = device_id
        self._name = name
        self._logic_addr = logic_addr
        self._device_name = dev_name
        self._config_entry = config_entry
        self._attr_device_class = device_class
        self._is_on = False

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
    def is_on(self) -> bool:
        return self._is_on

    async def update_state(self, state: LinSensorState) -> None:
        """Update state from device."""
        if isinstance(state, LinSensorState):
            self._is_on = state.get_value() == 0


