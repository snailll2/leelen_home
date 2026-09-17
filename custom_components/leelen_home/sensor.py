# -*- coding: utf-8 -*-

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorDeviceClass

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import LogUtils
from .leelen.common.LeelenType import LogicDeviceType
from .leelen.states.LinSensorState import LinSensorState
from .platform_helper import async_setup_entry as _setup_platform
from .state_subscription import StateUpdateSubscriber

_LOGGER = logging.getLogger(__name__)


def _build_entities(device_info, config_entry):
    """按 logic_type 建实体:温湿度/PM 传感器→Sensor,门磁/水浸→BinarySensor。"""
    entities = []
    for logic_srv in device_info.get("logic_srv", []):
        if logic_srv.get("logic_type") in [LogicDeviceType.TYPE_TEMPERATURE_SENSOR]:
            entities.append(Sensor(
                logic_srv.get("logic_addr"), logic_srv.get("dev_addr"),
                logic_srv.get("logic_name"), device_info.get("dev_name"),
                SensorDeviceClass.TEMPERATURE, "°C", config_entry))
        if logic_srv.get("logic_type") in [LogicDeviceType.TYPE_PM_SENSOR]:
            entities.append(Sensor(
                logic_srv.get("logic_addr"), logic_srv.get("dev_addr"),
                logic_srv.get("logic_name"), device_info.get("dev_name"),
                SensorDeviceClass.PM25, "µg/m³", config_entry))
        if logic_srv.get("logic_type") in [LogicDeviceType.TYPE_HUMIDITY_SENSOR]:
            entities.append(Sensor(
                logic_srv.get("logic_addr"), logic_srv.get("dev_addr"),
                logic_srv.get("logic_name"), device_info.get("dev_name"),
                SensorDeviceClass.HUMIDITY, "%", config_entry))
        if logic_srv.get("logic_type") in [LogicDeviceType.TYPE_WIRELESS_DOOR_SENSOR]:
            entities.append(BinarySensor(
                logic_srv.get("logic_addr"), logic_srv.get("dev_addr"),
                logic_srv.get("logic_name"), device_info.get("dev_name"),
                BinarySensorDeviceClass.DOOR, config_entry))
        if logic_srv.get("logic_type") in [LogicDeviceType.TYPE_WIRELESS_WATER_IMMERSION_SENSOR]:
            entities.append(BinarySensor(
                logic_srv.get("logic_addr"), logic_srv.get("dev_addr"),
                logic_srv.get("logic_name"), device_info.get("dev_name"),
                BinarySensorDeviceClass.MOISTURE, config_entry))
    return entities


async def async_setup_entry(
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up a config entry."""
    await _setup_platform(hass, config_entry, async_add_entities, _build_entities)


class Sensor(StateUpdateSubscriber, SensorEntity):

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
        


class BinarySensor(StateUpdateSubscriber, BinarySensorEntity):

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
            # 二进制传感器(门磁/水浸)的含义:设备上报值 0 表示「触发/门开」。
            # 若门磁/水浸实体在真机上方向相反(门开显示为关),需把 O 判定取反 —— 待真机验证。
            self._prop_on = state.get_value() == 0


