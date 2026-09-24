"""气候三分类适配单元测试(纯逻辑,不依赖 HA 运行时)。

覆盖:
- CommonModel 地暖电源位 bit4(0x10)解析、658/776 功能码映射
- AirConditioner 控制字节编码(与官方 App 一致)
- FreshAirFan level 0/1/2/3/0xFE 映射与功能码选择(774 vs 152)
- _build_entities 按 logic_type 分派三分类 + display 过滤

运行(在 wsl HA 容器):
    docker exec ha-test python3 -m pytest tests/test_climate_adaptation.py -q
"""
import asyncio
from unittest.mock import Mock, patch

from homeassistant.components.climate import (  # noqa: E402
    HVACMode, FAN_LOW, FAN_MEDIUM, FAN_HIGH, FAN_AUTO,
)

from custom_components.leelen_home.climate import (  # noqa: E402
    AirConditioner, FreshAirFan, FloorHeatingClimate, _build_entities,
    SUPPORTED_LOGIC_TYPES,
)
from custom_components.leelen_home.const import CLIMATE_LOGIC_TYPES  # noqa: E402
from custom_components.leelen_home.leelen.common.CommonModel import CommonModel  # noqa: E402
from custom_components.leelen_home.leelen.common.LeelenType import (  # noqa: E402
    FunctionType, LogicDeviceType,
)
from custom_components.leelen_home.leelen.models.ControlModel import ControlModel  # noqa: E402
from custom_components.leelen_home.leelen.states.LinCenterAcState import LinCenterAcState  # noqa: E402
from custom_components.leelen_home.leelen.states.LinSensorState import LinSensorState  # noqa: E402


def _mock_config_entry():
    return Mock(entry_id="test", data={})


class _FakeControlModel:
    def __init__(self, handler):
        self._handler = handler

    def device_control(self, service_id, control_type, control_data):
        self._handler(service_id, control_type, control_data)


# ---------------------------------------------------------------- CommonModel

def test_floor_heating_power_bit4_on():
    """地暖电源位 = 状态字节 bit4(0x10,官方 App 确认)。"""
    state = CommonModel.get_instance().get_cur_floor_heating_state(
        123, 51213, bytes([25, 0x10]))
    assert state.power_state == 1


def test_floor_heating_power_bit4_off():
    """bit4 = 0 时关;旧实现误读 bit0,0x01 会被当成开 —— 必须为关。"""
    state = CommonModel.get_instance().get_cur_floor_heating_state(
        123, 51234, bytes([25, 0x01]))
    assert state.power_state == 0


def test_function_id_658_center_ac():
    """658(ZigBee 中心空调)必须走 55297,不能落到默认 ON_OFF。"""
    assert (CommonModel.get_instance().get_function_id_by_service_type(
        LogicDeviceType.ZIGBEE_CENTER_AC, 0) == FunctionType.FUNCTION_CENTER_AC)


def test_function_id_776_floor_heating():
    """776(地板加热器)必须走 51213。"""
    assert (CommonModel.get_instance().get_function_id_by_service_type(
        LogicDeviceType.TYPE_FLOOR, 0) == FunctionType.FUNCTION_FLOOR_HEATING)


# ------------------------------------------------------------------ 分派建实体

def _device(logic_srvs):
    return {"dev_name": "测试设备", "dev_addr": 999, "logic_srv": logic_srvs}


def test_build_entities_dispatches_three_classes():
    """146 → AirConditioner、780 → FreshAirFan、775 → FloorHeatingClimate,
    unique_id 均为各自 logic_addr,且不按 dev_name 匹配。"""
    device_info = _device([
        {"logic_type": LogicDeviceType.TYPE_CENTER_AIR_CONDITIONER,  # 146
         "logic_addr": 1001, "dev_addr": 999, "logic_name": "客厅空调", "display": 1},
        {"logic_type": LogicDeviceType.DIY_REFRESH_AIR,  # 780
         "logic_addr": 1002, "dev_addr": 999, "logic_name": "新风", "display": 1},
        {"logic_type": LogicDeviceType.TYPE_FLOOR_ACTUATOR,  # 775
         "logic_addr": 1003, "dev_addr": 999, "logic_name": "主卧地暖", "display": 1},
    ])
    entities = _build_entities(device_info, _mock_config_entry())
    assert len(entities) == 3
    classes = {type(e) for e in entities}
    assert classes == {AirConditioner, FreshAirFan, FloorHeatingClimate}
    unique_ids = {e.unique_id for e in entities}
    assert unique_ids == {"leelen_logic_addr_1001",
                          "leelen_logic_addr_1002",
                          "leelen_logic_addr_1003"}


def test_build_entities_respects_display_zero():
    """display=0 的逻辑服务(官方 App 隐藏的面板重复通道)不建实体。"""
    device_info = _device([
        {"logic_type": LogicDeviceType.TYPE_AC_ACTUATOR,  # 773
         "logic_addr": 2001, "dev_addr": 999, "logic_name": "面板空调", "display": 0},
        {"logic_type": LogicDeviceType.TYPE_AC_ACTUATOR,
         "logic_addr": 2002, "dev_addr": 999, "logic_name": "正常空调", "display": 1},
    ])
    entities = _build_entities(device_info, _mock_config_entry())
    assert len(entities) == 1
    assert entities[0].unique_id == "leelen_logic_addr_2002"


def test_build_entities_ignores_other_types():
    """非气候 logic_type 不建实体。"""
    device_info = _device([
        {"logic_type": LogicDeviceType.TYPE_WIRELESS_LIGHT,  # 灯
         "logic_addr": 3001, "dev_addr": 999, "logic_name": "灯", "display": 1},
    ])
    assert _build_entities(device_info, _mock_config_entry()) == []


def test_supported_types_matches_const_full_set():
    """SUPPORTED_LOGIC_TYPES 必须覆盖 const 全集(保测试断言不漂移)。"""
    assert SUPPORTED_LOGIC_TYPES == CLIMATE_LOGIC_TYPES
    assert {146, 773, 774, 775, 776, 777, 148, 150, 152, 157,
            242, 658, 662, 664, 770, 771, 772, 778, 779, 780, 782, 783} <= set(
                CLIMATE_LOGIC_TYPES)


# --------------------------------------------------------------- AirConditioner

def test_ac_byte_encoding_cool_high_24():
    """power=1, mode=COOL(2), speed=HIGH(3), temp=24 →
    byte0=(3<<5)|8=0x68, byte1=(1<<3)|2=0x0A(与官方 App 编码一致)。"""
    entity = AirConditioner(1001, 999, "空调", "设备", _mock_config_entry(),
                            LogicDeviceType.TYPE_CENTER_AIR_CONDITIONER)
    entity._prop_on = True
    entity._attr_hvac_mode = HVACMode.COOL
    entity._attr_fan_mode = FAN_HIGH
    entity._attr_target_temperature = 24.0
    captured = {}

    def _fake_device_control(addr, func, data):
        captured["addr"] = addr
        captured["func"] = func
        captured["data"] = data

    with patch.object(ControlModel, "get_instance",
                      return_value=_FakeControlModel(_fake_device_control)):
        asyncio.run(entity._send_control())

    assert captured["addr"] == 1001
    assert captured["func"] == FunctionType.FUNCTION_CENTER_AC
    assert captured["data"] == bytes([0x68, 0x0A])


def test_ac_actuator_type_uses_51232():
    """773/778(空调执行器)控制功能码应为 51232。"""
    entity = AirConditioner(2001, 999, "执行器空调", "设备", _mock_config_entry(),
                            LogicDeviceType.TYPE_AC_ACTUATOR)
    assert entity._control_func == FunctionType.FUNCTION_AC_ACTUATOR


def test_ac_update_state_roundtrip():
    """上报 0x68/0x0A 应回写 mode=COOL、speed=HIGH、temp=24、prop_on。"""
    entity = AirConditioner(1001, 999, "空调", "设备", _mock_config_entry(),
                            LogicDeviceType.TYPE_CENTER_AIR_CONDITIONER)
    state = CommonModel.get_instance().get_cur_center_ac_state(
        1001, 55297, bytes([0x68, 0x0A]))
    asyncio.run(entity.update_state(state))
    assert entity._prop_on is True
    assert entity._attr_hvac_mode == HVACMode.COOL
    assert entity._attr_fan_mode == FAN_HIGH
    assert entity._attr_target_temperature == 24


def test_ac_room_temp_sensor_state():
    """FUNCTION_AC_TEMP(22529)上报刷新室温。"""
    entity = AirConditioner(1001, 999, "空调", "设备", _mock_config_entry(),
                            LogicDeviceType.TYPE_CENTER_AIR_CONDITIONER)
    state = LinSensorState()
    state.service_type = FunctionType.FUNCTION_AC_TEMP
    state.value = 27
    asyncio.run(entity.update_state(state))
    assert entity._attr_current_temperature == 27


# ---------------------------------------------------------------- FreshAirFan

def test_fresh_actuator_type_uses_49185():
    """774/780(新风执行器)控制功能码应为 49185。"""
    entity = FreshAirFan(1002, 999, "新风", "设备", _mock_config_entry(),
                         LogicDeviceType.TYPE_FRESH_ACTUATOR)
    assert entity._control_func == FunctionType.FUNCTION_FRESH_ACTUATOR


def test_fresh_other_type_uses_49156():
    """152 等非执行器新风控制功能码应为 49156。"""
    entity = FreshAirFan(1002, 999, "新风", "设备", _mock_config_entry(),
                         LogicDeviceType.TYPE_REFRESH_AIR)
    assert entity._control_func == FunctionType.FUNCTION_LEVEL_GEARS


def test_fresh_level_payload_mapping():
    """level 0/1/2/3/0xFE → 关/低/中/高/自动的单字节载荷。"""
    cases = [(0, 0x00), (1, 0x01), (2, 0x02), (3, 0x03), (0xFE, 0xFE)]
    for level, expected in cases:
        entity = FreshAirFan(1002, 999, "新风", "设备", _mock_config_entry(),
                             LogicDeviceType.TYPE_FRESH_ACTUATOR)
        entity._speed_level = level
        entity._prop_on = level != 0
        captured = {}

        def _fake(addr, func, data):
            captured["data"] = data

        with patch.object(ControlModel, "get_instance",
                          return_value=_FakeControlModel(_fake)):
            asyncio.run(entity._send_control())
        assert captured["data"] == bytes([expected]), f"level={level}"


def test_fresh_update_state_level_mapping():
    """上报首字节 level 值应映射到对应 fan_mode 与开关态。"""
    cases = [
        (0, FAN_LOW, False),
        (1, FAN_LOW, True),
        (2, FAN_MEDIUM, True),
        (3, FAN_HIGH, True),
        (0xFE, FAN_AUTO, True),
    ]
    for val, fan_mode, prop_on in cases:
        entity = FreshAirFan(1002, 999, "新风", "设备", _mock_config_entry(),
                             LogicDeviceType.TYPE_FRESH_ACTUATOR)
        state = LinCenterAcState()
        state.service_type = FunctionType.FUNCTION_FRESH_ACTUATOR
        state.power_state = val
        state.state = bytes([val])
        asyncio.run(entity.update_state(state))
        assert entity._attr_fan_mode == fan_mode, f"val={val}"
        assert entity._prop_on is prop_on, f"val={val}"


# ------------------------------------------------------------ FloorHeatingClimate

def test_floor_uses_51213_for_type_776():
    """776(地板加热器)控制功能码应为 51213。"""
    entity = FloorHeatingClimate(1003, 999, "地暖", "设备", _mock_config_entry(),
                                 LogicDeviceType.TYPE_FLOOR)
    assert entity._control_func == FunctionType.FUNCTION_FLOOR_HEATING


def test_floor_uses_51234_for_type_775():
    """775(地暖执行器)控制功能码应为 51234。"""
    entity = FloorHeatingClimate(1003, 999, "地暖", "设备", _mock_config_entry(),
                                 LogicDeviceType.TYPE_FLOOR_ACTUATOR)
    assert entity._control_func == FunctionType.FUNCTION_FLOOR_ACTUATOR


def test_floor_update_state_bit4_and_temp():
    """上报 [22, 0x10] → 温度 22、开。"""
    entity = FloorHeatingClimate(1003, 999, "地暖", "设备", _mock_config_entry(),
                                 LogicDeviceType.TYPE_FLOOR)
    state = LinCenterAcState()
    state.service_type = FunctionType.FUNCTION_FLOOR_HEATING
    state.state = bytes([22, 0x10])
    state.power_state = 1
    asyncio.run(entity.update_state(state))
    assert entity._attr_target_temperature == 22.0
    assert entity._prop_on is True
    assert entity._last_state_byte == 0x10


def test_floor_turn_on_sets_bit4_and_temp():
    """开关帧把 bit4 置位同时带设定温度,发到自身地址。"""
    entity = FloorHeatingClimate(1003, 999, "地暖", "设备", _mock_config_entry(),
                                 LogicDeviceType.TYPE_FLOOR)
    entity._last_state_byte = 0x00
    entity._attr_target_temperature = 22.0
    entity._prop_on = True
    captured = {}

    def _fake(addr, func, data):
        captured["addr"] = addr
        captured["func"] = func
        captured["data"] = data

    with patch.object(ControlModel, "get_instance",
                      return_value=_FakeControlModel(_fake)):
        asyncio.run(entity._send_control())
    assert captured["addr"] == 1003
    assert captured["func"] == FunctionType.FUNCTION_FLOOR_HEATING
    assert captured["data"] == bytes([22, 0x10])