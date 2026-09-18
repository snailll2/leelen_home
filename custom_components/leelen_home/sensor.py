# -*- coding: utf-8 -*-

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorDeviceClass

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity_base import LeelenEntity
from .leelen.common.LeelenType import LogicDeviceType
from .leelen.states.LinSensorState import LinSensorState
from .leelen.utils.LogUtils import LogUtils
from .platform_helper import async_setup_entry as _setup_platform



#: sensor 平台的 logic_type → (device_class, 单位, 是否二元传感器)。
#: 键集合需与 const.SENSOR_LOGIC_TYPES 保持一致(后者供「同步设备」统计判定使用),
#: tests/test_integration.py 里有断言守住这一点。
_SENSOR_SPECS = {
    LogicDeviceType.TYPE_TEMPERATURE_SENSOR: (SensorDeviceClass.TEMPERATURE, "°C", False),
    LogicDeviceType.TYPE_PM_SENSOR: (SensorDeviceClass.PM25, "µg/m³", False),
    LogicDeviceType.TYPE_HUMIDITY_SENSOR: (SensorDeviceClass.HUMIDITY, "%", False),
    LogicDeviceType.TYPE_WIRELESS_DOOR_SENSOR: (BinarySensorDeviceClass.DOOR, None, True),
    LogicDeviceType.TYPE_WIRELESS_WATER_IMMERSION_SENSOR: (
        BinarySensorDeviceClass.MOISTURE, None, True),
}


def _build_entities(device_info, config_entry):
    """按 logic_type 建实体:温湿度/PM 传感器→Sensor,门磁/水浸→BinarySensor。"""
    entities = []
    for logic_srv in device_info.get("logic_srv", []):
        spec = _SENSOR_SPECS.get(logic_srv.get("logic_type"))
        if spec is None:
            continue
        device_class, unit_of_measurement, is_binary = spec
        entity_cls = BinarySensor if is_binary else Sensor
        entities.append(entity_cls(
            logic_srv.get("logic_addr"),
            logic_srv.get("dev_addr"),
            logic_srv.get("logic_name"),
            device_info.get("dev_name"),
            device_class,
            unit_of_measurement,
            config_entry))
    return entities


async def async_setup_entry(
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up a config entry."""
    await _setup_platform(hass, config_entry, async_add_entities, _build_entities)


class Sensor(LeelenEntity, SensorEntity):

    def __init__(self, logic_addr, device_id: str, name: str, dev_name: str,
                 device_class, unit_of_measurement: str, config_entry: ConfigEntry):
        super().__init__(logic_addr, device_id, name, dev_name, config_entry)
        self._attr_device_class = device_class
        self._attr_native_unit_of_measurement = unit_of_measurement

    @property
    def native_value(self) -> Any:
        """Return the current value of the sensor."""
        return self._attr_native_value

    async def update_state(self, state: LinSensorState):
        LogUtils.d(f"update {state}")
        if isinstance(state, LinSensorState):
            self._attr_native_value = state.get_value()


class BinarySensor(LeelenEntity, BinarySensorEntity):

    # 与 Sensor 保持同一构造签名,便于 _build_entities 用同一份规格表统一实例化。
    def __init__(self, logic_addr, device_id: str, name: str, dev_name: str,
                 device_class, unit_of_measurement: str | None = None,
                 config_entry: ConfigEntry | None = None):
        super().__init__(logic_addr, device_id, name, dev_name, config_entry)
        self._attr_device_class = device_class

    async def update_state(self, state: LinSensorState):
        if isinstance(state, LinSensorState):
            # 二进制传感器(门磁/水浸)的含义:设备上报值 0 表示「触发/门开」。
            # 若门磁/水浸实体在真机上方向相反(门开显示为关),需把 0 判定取反 —— 待真机验证。
            self._prop_on = state.get_value() == 0
