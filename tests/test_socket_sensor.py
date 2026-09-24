"""智能插座(518)独立电参数 sensor 实体测试。

覆盖(B 方案:Switch 属性之外,额外建 3 个页面可见的 sensor 实体):
- ``sensor._build_entities``:518 逻辑通道展开成 3 个 ``SocketSensor``
  (功率/今日用电/本月用电),非 518 通道仍走原 ``_SENSOR_SPECS`` 通用路径
- ``SocketSensor.unique_id``:带功能后缀,避免与 switch 平台裸 ID 撞车
- ``SocketSensor.update_state``:按 (kind, service_type) 分支 ——
  20517×0.1→W、22556→今日 kWh、22557→本月 kWh,其余 service_type 忽略
- ``state_subscription._handle_state_event``:按 ``_logic_addr`` 匹配(非 unique_id
  字符串),后缀 unique_id 的传感器也能收到事件 —— 本方案的地基改动
- ``config_flow._collect_expected_unique_ids``:all_entities 含 3 个后缀 ID,
  「同步设备」清理不会误删新 sensor 实体

运行(在 wsl HA 容器):
    docker exec ha-test python3 -m pytest tests/test_socket_sensor.py -q
"""
import asyncio
import sys
import unittest
from datetime import datetime
from unittest.mock import Mock, patch

sys.path.insert(0, "/config")

from custom_components.leelen_home.sensor import _build_entities, SocketSensor, SOCKET_ENERGY_SUFFIXES  # noqa: E402
from custom_components.leelen_home.config_flow import _collect_expected_unique_ids  # noqa: E402
from custom_components.leelen_home.leelen.common.CommonModel import CommonModel  # noqa: E402
from custom_components.leelen_home.leelen.common.LeelenType import (  # noqa: E402
    FunctionType, LogicDeviceType,
)
from custom_components.leelen_home.leelen.models.MsgStorageModel import MsgStorageModel  # noqa: E402
from custom_components.leelen_home.leelen.states.LinSensorState import LinSensorState  # noqa: E402


# 逻辑地址 33/49/289/353/369 为用户真实网关的 5 台智能插座(dump.db 确认)。
SOCKET_A = 33


def _mock_config_entry():
    return Mock(entry_id="test", data={})


def _reset_singletons():
    """重置受测单例,避免用例间缓存串扰。"""
    MsgStorageModel.reset_instance()
    CommonModel.reset_instance()


def _frozen_now(cls_at):
    """把被 patch 模块里的 datetime 换成 now() 固定的假时钟。"""
    class _FrozenDatetime:
        fixed = cls_at

        @classmethod
        def now(cls):
            return cls.fixed

    return _FrozenDatetime


def _socket_device_info(addr=SOCKET_A, name="插座A", extra=None):
    """含一个 518 通道的假设备(可选再挂一个普通传感器通道)。"""
    logic_srv = [
        {"logic_type": LogicDeviceType.ZIGBEE_SMART_WALL_SOCKET,
         "logic_addr": addr, "dev_addr": f"d{addr}", "logic_name": name},
    ]
    if extra:
        logic_srv.append(extra)
    return {"dev_name": "插座设备", "logic_srv": logic_srv}


# ------------------------------------------------------------ _build_entities

class TestBuildSocketEntities(unittest.TestCase):
    def setUp(self):
        _reset_singletons()

    def tearDown(self):
        _reset_singletons()

    def test_518_expands_to_three_socket_sensors(self):
        entities = _build_entities(_socket_device_info(), _mock_config_entry())
        assert len(entities) == 3, entities
        for ent in entities:
            assert isinstance(ent, SocketSensor)
            assert ent._logic_addr == SOCKET_A

        by_suffix = {ent._unique_suffix: ent for ent in entities}
        assert set(by_suffix) == set(SOCKET_ENERGY_SUFFIXES)

        power = by_suffix["current_power_w"]
        assert power.unique_id == f"leelen_logic_addr_{SOCKET_A}_current_power_w"
        assert power.name == "插座A 当前功率"
        assert power.device_class == "power"
        assert power.native_unit_of_measurement == "W"
        assert power._attr_state_class == "measurement"

        today = by_suffix["today_energy_kwh"]
        assert today.unique_id == f"leelen_logic_addr_{SOCKET_A}_today_energy_kwh"
        assert today.name == "插座A 今日用电"
        assert today.device_class == "energy"
        assert today.native_unit_of_measurement == "kWh"
        # energy 设备类配 MEASUREMENT 会触发 HA 告警 → 周期快照值显式无 state_class
        assert today._attr_state_class is None
        assert today._kind == "today"

        month = by_suffix["month_energy_kwh"]
        assert month.unique_id == f"leelen_logic_addr_{SOCKET_A}_month_energy_kwh"
        assert month.name == "插座A 本月用电"
        assert month.device_class == "energy"
        assert month.native_unit_of_measurement == "kWh"
        assert month._attr_state_class is None
        assert month._kind == "month"

    def test_non_518_channel_keeps_generic_spec(self):
        # 518 与普通温度传感器同设备:插座展开 3 个,温度仍走原 _SENSOR_SPECS。
        from custom_components.leelen_home.sensor import Sensor
        device_info = _socket_device_info(extra={
            "logic_type": LogicDeviceType.TYPE_TEMPERATURE_SENSOR,
            "logic_addr": 4400, "dev_addr": "d4400", "logic_name": "温度",
        })
        entities = _build_entities(device_info, _mock_config_entry())
        assert len(entities) == 4, entities
        sockets = [e for e in entities if isinstance(e, SocketSensor)]
        generic = [e for e in entities if not isinstance(e, SocketSensor)]
        assert len(sockets) == 3
        assert len(generic) == 1
        assert isinstance(generic[0], Sensor)
        assert generic[0].unique_id == "leelen_logic_addr_4400"
        assert generic[0].device_class == "temperature"


# --------------------------------------------------------- SocketSensor.update_state

class TestSocketSensorUpdateState(unittest.TestCase):
    def setUp(self):
        _reset_singletons()

    def tearDown(self):
        _reset_singletons()

    def _make(self, kind, suffix):
        return SocketSensor(SOCKET_A, f"d{SOCKET_A}", "插座A", "插座设备",
                            kind, kind, None if kind != "power" else "power",
                            None if kind == "power" else "kWh", _mock_config_entry(), suffix)

    def test_power_branch_scales_raw_counter(self):
        sensor = self._make("power", "current_power_w")
        state = LinSensorState()
        state.set_service_type(FunctionType.FUNCTION_POWER)
        state.set_power(260)  # 原始值 260 → ×0.1 → 26.0 W
        asyncio.run(sensor.update_state(state))
        assert sensor.native_value == 26.0

    def test_today_branch_passthrough(self):
        sensor = self._make("today", "today_energy_kwh")
        state = LinSensorState()
        state.set_service_type(FunctionType.FUNCTION_SMART_SOCKET_HOUR_POWER)
        state.set_power(2.3456)  # 状态即 kWh
        asyncio.run(sensor.update_state(state))
        assert sensor.native_value == 2.3456

    def test_month_branch_passthrough(self):
        sensor = self._make("month", "month_energy_kwh")
        state = LinSensorState()
        state.set_service_type(FunctionType.FUNCTION_SMART_SOCKET_DAY_POWER)
        state.set_power(10.5)
        asyncio.run(sensor.update_state(state))
        assert sensor.native_value == 10.5

    def test_wrong_kind_service_type_ignored(self):
        # 22556(今日)打向 power 类实体 → 不改值(事件仍会写 HA 状态,但值保持 None)。
        sensor = self._make("power", "current_power_w")
        state = LinSensorState()
        state.set_service_type(FunctionType.FUNCTION_SMART_SOCKET_HOUR_POWER)
        state.set_power(2.34)
        asyncio.run(sensor.update_state(state))
        assert sensor.native_value is None

    def test_non_sensor_state_ignored(self):
        sensor = self._make("power", "current_power_w")
        asyncio.run(sensor.update_state(None))
        assert sensor.native_value is None


# ---------------------------------------- _handle_state_event 按逻辑地址匹配

def _make_event(logic_address=SOCKET_A, function_id=None, state=b""):
    event = Mock()
    event.logic_address = logic_address
    event.function_id = function_id
    event.state = state
    return event


class TestHandleStateEventSuffixedMatch(unittest.TestCase):
    """`_handle_state_event` 按 _logic_addr 匹配 —— 后缀 unique_id 也能收到事件。"""

    def setUp(self):
        _reset_singletons()

    def tearDown(self):
        _reset_singletons()

    def test_power_event_updates_power_sensor(self):
        sensor = SocketSensor(SOCKET_A, f"d{SOCKET_A}", "插座A", "插座设备",
                              "power", "当前功率", "power", "W",
                              _mock_config_entry(), "current_power_w")
        with patch.object(sensor, "async_write_ha_state", new=Mock()):
            asyncio.run(sensor._handle_state_event(
                _make_event(function_id=FunctionType.FUNCTION_POWER,
                            state=b"\x04\x01\x00\x00")))  # 0x0104 = 260 → 26.0 W
        assert sensor.native_value == 26.0

    def test_today_event_updates_today_sensor(self):
        model = MsgStorageModel.get_instance()
        model.upsert(SOCKET_A, 22556, "2026-09-24 08:00:00", (9_000_000).to_bytes(6, "little"))
        model.upsert(SOCKET_A, 22556, "2026-09-24 12:00:00", (9_003_333).to_bytes(6, "little"))

        sensor = SocketSensor(SOCKET_A, f"d{SOCKET_A}", "插座A", "插座设备",
                              "today", "今日用电", "energy", "kWh",
                              _mock_config_entry(), "today_energy_kwh")
        now = datetime(2026, 9, 24, 20, 0, 0)
        with patch("custom_components.leelen_home.leelen.common.CommonModel.datetime",
                   new=_frozen_now(now)), \
             patch.object(sensor, "async_write_ha_state", new=Mock()):
            asyncio.run(sensor._handle_state_event(
                _make_event(function_id=FunctionType.FUNCTION_SMART_SOCKET_HOUR_POWER)))
        assert sensor.native_value == 0.333  # 3333/10000 → 3 位 ROUND_HALF_UP

    def test_other_logic_address_ignored(self):
        # 事件属于另一台插座(不同逻辑地址):本传感器不更新。
        sensor = SocketSensor(SOCKET_A, f"d{SOCKET_A}", "插座A", "插座设备",
                              "power", "当前功率", "power", "W",
                              _mock_config_entry(), "current_power_w")
        model = MsgStorageModel.get_instance()
        model.upsert(SOCKET_A, 22556, "2026-09-24 08:00:00", (9_000_000).to_bytes(6, "little"))
        model.upsert(SOCKET_A, 22556, "2026-09-24 12:00:00", (9_003_333).to_bytes(6, "little"))
        with patch("custom_components.leelen_home.leelen.common.CommonModel.datetime",
                   new=_frozen_now(datetime(2026, 9, 24, 20, 0, 0))), \
             patch.object(sensor, "async_write_ha_state", new=Mock()):
            # 事件指向 SOCKET_B(353):今天有小时行,但地址不匹配 → 忽略
            asyncio.run(sensor._handle_state_event(
                _make_event(logic_address=353,
                            function_id=FunctionType.FUNCTION_SMART_SOCKET_HOUR_POWER)))
        assert sensor.native_value is None


# ---------------------------------------------------- config_flow all_entities

class TestCollectExpectedUniqueIds(unittest.TestCase):
    def test_socket_adds_three_suffixed_ids(self):
        devices = [
            {"logic_srv": [
                {"logic_type": LogicDeviceType.ZIGBEE_SMART_WALL_SOCKET,
                 "logic_addr": 33, "dev_addr": 32, "logic_name": "A"},
                {"logic_type": LogicDeviceType.ZIGBEE_SMART_WALL_SOCKET,
                 "logic_addr": 34, "dev_addr": 32, "logic_name": "B"},
            ]},
        ]
        got = _collect_expected_unique_ids(devices)
        # 裸 ID 每通道一条
        assert "leelen_logic_addr_33" in got
        assert "leelen_logic_addr_34" in got
        # 每台插座额外含 3 个后缀 ID(「同步设备」清理不误删它们的依据)
        for suffix in SOCKET_ENERGY_SUFFIXES:
            assert f"leelen_logic_addr_33_{suffix}" in got, suffix
            assert f"leelen_logic_addr_34_{suffix}" in got, suffix

    def test_non_socket_no_suffixed_ids(self):
        devices = [
            {"logic_srv": [
                {"logic_type": LogicDeviceType.TYPE_WIRELESS_CURTAIN,
                 "logic_addr": 55, "dev_addr": "c", "logic_name": "C"},
            ]},
        ]
        got = _collect_expected_unique_ids(devices)
        # 裸 ID 每通道一条;非插座不给电参数后缀 ID(sync 清理的误删依据)。
        assert "leelen_logic_addr_55" in got
        for suffix in SOCKET_ENERGY_SUFFIXES:
            assert not any(uid.endswith(f"_{suffix}") for uid in got), suffix
        # 设备 dict 无 dev_addr(None)时不得产出定位 id(如 leelen_device_locate_None)。
        assert not any(uid.startswith("leelen_device_locate_") for uid in got), got

    def test_empty_devices_empty_set(self):
        assert _collect_expected_unique_ids([]) == set()


if __name__ == "__main__":
    unittest.main()