# -*- coding: utf-8 -*-

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorDeviceClass

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity_base import LeelenEntity
from .leelen.common.LeelenType import FunctionType, LogicDeviceType, PropertyId
from .leelen.states.LinSensorState import LinSensorState
from .leelen.utils.ConvertUtils import ConvertUtils
from .leelen.utils.LogUtils import LogUtils
from .platform_helper import async_setup_entry as _setup_platform
from .state_subscription import gateway_link_up



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
    # 智能插座(518):占位以满足「键集 == SENSOR_LOGIC_TYPES」断言。真正的 3 个
    # 电参数传感器由 _build_entities 的 518 分支展开(见 _SOCKET_ENERGY_SENSORS),
    # 不经过这张「1 逻辑通道 1 实体」的规格表。
    LogicDeviceType.ZIGBEE_SMART_WALL_SOCKET: (None, None, False),
}

#: 智能插座(518)电参数传感器的展开规格:每个 518 逻辑通道建 3 个 sensor 实体。
#: 字段:(kind, unique_id 后缀, 显示标签, device_class, 单位)。
#: kind 决定 update_state 认哪个 function_id;即 unique_id 的后缀部分;标签拼进
#: 显示名 —— 三个实体同 logic_name,显示名必须互不相同,否则 entity_id 撞车。
_SOCKET_ENERGY_SENSORS = (
    ("power", "current_power_w", "当前功率", SensorDeviceClass.POWER, "W"),
    ("today", "today_energy_kwh", "今日用电", SensorDeviceClass.ENERGY, "kWh"),
    ("month", "month_energy_kwh", "本月用电", SensorDeviceClass.ENERGY, "kWh"),
)
#: 518 实体 unique_id 的后缀集合,供 config_flow 的「同步设备」清理逻辑把它们
#: 计入 all_entities(否则会被误删)。
SOCKET_ENERGY_SUFFIXES = tuple(spec[1] for spec in _SOCKET_ENERGY_SENSORS)

#: 网关(dev_addr==0)属性实体的展开规格:字段 (unique_id 后缀, 显示标签, property_id)。
#: value 来自设备库 property_tbl addr=0 行的 all_property;PropertyId 常量见 LeelenType。
#: 下方注释仅作值格式示例,非真实环境数据(已脱敏)。
_GATEWAY_ATTR_SENSORS = (
    ("main_version", "主版本",   PropertyId.GW_VER_PROPERTY_ID),        # "3.12"
    ("soft_version", "软件版本", PropertyId.GW_LITTLE_VER_PROPERTY_ID), # "V1.02-181107"
    ("ip",           "IP地址",   PropertyId.GW_ADDR_PROPERTY_ID),       # "192.0.2.135"
    ("mac",          "MAC地址",  PropertyId.GATEWAY_MAC),               # "AA:BB:CC:DD:EE:FF"
    ("ssid",         "WiFi名称", PropertyId.WIRELESS_SSID),             # "Home_WiFi"
)
#: 网关属性实体 unique_id 后缀集合 + 在线实体唯一 id,供 config_flow 清理白名单复用。
GATEWAY_ATTR_SUFFIXES = tuple(spec[0] for spec in _GATEWAY_ATTR_SENSORS)
GATEWAY_ONLINE_UNIQUE_ID = "leelen_gateway_online"


def _value_to_text(val) -> str | None:
    """把 all_property 的 val(bytes / str / None)归一成可读文本。"""
    if val is None:
        return None
    if isinstance(val, str):
        return val or None
    if isinstance(val, (bytes, bytearray)):
        text = ConvertUtils.byte_array_to_utf8_string(bytes(val))
        return text or None
    return str(val)


def _build_entities(device_info, config_entry):
    """按 logic_type 建实体:温湿度/PM 传感器→Sensor,门磁/水浸→BinarySensor,
    智能插座(518)→3 个电参数传感器(功率/今日用电/本月用电);
    网关设备(dev_addr==0)→网关属性/在线实体。"""
    if str(device_info.get("dev_addr")) == "0":
        return _build_gateway_entities(device_info, config_entry)
    entities = []
    for logic_srv in device_info.get("logic_srv", []):
        if logic_srv.get("logic_type") == LogicDeviceType.ZIGBEE_SMART_WALL_SOCKET:
            # 智能插座:数据源与 switch 平台同一批 20517/22556/22557 状态事件,
            # socket.sensor 按 kind 各取所需(不另发请求、不建重复连接)。
            for kind, suffix, label, device_class, unit in _SOCKET_ENERGY_SENSORS:
                entities.append(SocketSensor(
                    logic_srv.get("logic_addr"),
                    logic_srv.get("dev_addr"),
                    logic_srv.get("logic_name"),
                    device_info.get("dev_name"),
                    kind, label, device_class, unit, config_entry, suffix))
            continue
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


def _build_gateway_entities(device_info, config_entry):
    """为网关设备(dev_addr==0)建实体:版本/IP/MAC/WiFi 等属性 sensor + 在线 binary_sensor。

    值与网关归属于同一 device registry 条目(device_id="0",name=设备名,
    与 4139/4140 VSwitch 同设备)。属性值取自设备库 property_tbl addr=0 行。
    """
    dev_addr = device_info.get("dev_addr")
    dev_name = device_info.get("dev_name") or "网关"
    props = {}
    for row in device_info.get("all_property", []):
        props[row.get("property_id")] = row.get("val")

    entities = []
    for key, label, property_id in _GATEWAY_ATTR_SENSORS:
        value = _value_to_text(props.get(property_id))
        if value is None:
            continue  # 属性缺失(如老版本固件没有该属性)时不建空实体
        entities.append(GatewayAttrSensor(
            dev_addr, dev_name, key, label, value, config_entry))
    entities.append(GatewayOnlineSensor(dev_addr, dev_name, config_entry))
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


class SocketSensor(Sensor):
    """智能插座(518)电参数传感器:当前功率(W)/今日用电(kWh)/本月用电(kWh)。

    与 switch 平台的 Switch 消费同一批状态事件(逻辑地址相同),按 kind 各取所需:
    - power:20517(4 字节小端原始计数值,×0.1 → 瓦特,官方 App 口径);
    - today:22556(今日用电,状态即 kWh);
    - month:22557(本月用电,状态即 kWh)。

    值来源是 CommonModel.get_cur_state 算好的 ``LinSensorState.power``,
    不复刻任何解析/单位换算逻辑(与 Switch.extra_state_attributes 同源,天然一致)。
    """

    def __init__(self, logic_addr, device_id: str, name: str, dev_name: str,
                 kind: str, label: str, device_class, unit_of_measurement: str,
                 config_entry: ConfigEntry, unique_suffix: str):
        super().__init__(logic_addr, device_id, name, dev_name,
                         device_class, unit_of_measurement, config_entry)
        self._kind = kind
        self._label = label
        self._unique_suffix = unique_suffix
        # state_class:功率是可测瞬时量 → MEASUREMENT;今日/本月用电是「周期快照值」
        # (非累加表读数,每日/每月会重置,不满足 total* 的单调性)。energy 设备类配
        # MEASUREMENT 会触发 HA 的 device_class/state_class 组合告警,故显式置 None。
        self._attr_state_class = (
            SensorStateClass.MEASUREMENT if kind == "power" else None
        )

    @property
    def unique_id(self):
        """带功能后缀,避免与 switch/其他平台同吃裸 ID 而互相跳过。"""
        return f"leelen_logic_addr_{self._logic_addr}_{self._unique_suffix}"

    @property
    def name(self):
        # 三个实体同 logic_name;显示名带各自标签,避免 entity_id 撞车。
        return f"{self._name} {self._label}"

    async def update_state(self, state: LinSensorState):
        if not isinstance(state, LinSensorState):
            return
        service_type = state.get_service_type()
        value = None
        if self._kind == "power" and service_type == FunctionType.FUNCTION_POWER:
            # 20517 原始计数值 ×0.1 → 瓦特(1 位小数,与 Switch.current_power_w 一致)
            value = round((state.get_power() or 0) * 0.1, 1)
        elif self._kind == "today" and service_type == FunctionType.FUNCTION_SMART_SOCKET_HOUR_POWER:
            # 今日用电 22556:状态本身就是 kWh(3 位小数,与 Switch.today_energy_kwh 一致)
            value = state.get_power()
        elif self._kind == "month" and service_type == FunctionType.FUNCTION_SMART_SOCKET_DAY_POWER:
            # 本月用电 22557:状态本身就是 kWh(1 位小数,与 Switch.month_energy_kwh 一致)
            value = state.get_power()
        if value is None:
            # 非本实体关注的 function_id(比如 22556 打到 power 类),忽略。
            return
        LogUtils.d(f"💡 {self._name} {self._kind} update {value}")
        self._attr_native_value = value


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


class GatewayAttrSensor(LeelenEntity, SensorEntity):
    """网关属性 sensor(主版本 / 软件版本 / IP / MAC / WiFi 名)。

    值来自设备库 property_tbl addr=0 行,随「同步设备」刷新时可更新;无实时推送,故
    ``_logic_addr=None`` —— ``_handle_state_event`` 里 ``None != log地址`` 天然短路。
    可用性(available)与在线实体同源 ``gateway_link_up()``。
    """

    def __init__(self, device_id, dev_name: str, key: str, label: str,
                 value: str, config_entry: ConfigEntry):
        # device_id 保持设备库原始类型(int),与 switch/light 等平台一致,
        # 否则 ("LEELEN_HOME", 0) 与 ("LEELEN_HOME", "0") 会被设备注册表当成两个设备。
        super().__init__(None, device_id, dev_name, dev_name, config_entry)
        self._key = key
        self._label = label
        self._attr_native_value = value

    @property
    def unique_id(self) -> str:
        return f"leelen_gateway_attr_{self._key}"

    @property
    def name(self) -> str:
        return f"{self._device_name} {self._label}"


class GatewayOnlineSensor(LeelenEntity, BinarySensorEntity):
    """网关在线 binary_sensor:状态即链路是否已登录(gateway_link_up)。"""

    def __init__(self, device_id, dev_name: str, config_entry: ConfigEntry):
        # device_id 保持设备库原始类型(int),见 GatewayAttrSensor 说明。
        super().__init__(None, device_id, dev_name, dev_name, config_entry)
        self._attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    @property
    def unique_id(self) -> str:
        return GATEWAY_ONLINE_UNIQUE_ID

    @property
    def name(self) -> str:
        return f"{self._device_name} 在线"

    @property
    def is_on(self) -> bool:
        return gateway_link_up()