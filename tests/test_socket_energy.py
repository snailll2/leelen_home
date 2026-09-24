"""插座功率 / 用电量统计测试:MsgStorageModel 纯算法 + 解析链路 + Switch 属性。

覆盖(与官方 App 逆向结论逐条对齐):
- ``six_byte_to_long``:6 字节小端累计计数(高位补 0)
- ``today_energy``:22556(小时)首尾计数差 /10000,不足 2 行→0,负数钳 0,3 位小数
- ``month_energy``:22557(日)按天分桶(每组取相邻行对末对,覆盖式)、当日桶用
  今日值覆盖、求和 1 位小数
- ``AckToDao.trans_msg_storage_data``:CSV 电能行解析 → 合并进缓存 → 每插座派发
  22556/22557 两个事件
- ``CommonModel.get_cur_state`` 22556/22557 分支即时算 kWh
- ``DeviceStateModel.get_power_state``:len==4 才解析(官方守卫)
- ``Switch.update_state``:20517×0.1→W、22556→today、22557→month,标准属性输出
- ``fetch_msg_storage_data``:fetch 目标表/参数正确

运行(在 wsl HA 容器):
    docker exec ha-test python3 -m pytest tests/test_socket_energy.py -q
"""
import asyncio
import base64
import sys
import unittest
from datetime import datetime
from unittest.mock import Mock, patch

sys.path.insert(0, "/config")

from custom_components.leelen_home.switch import Switch  # noqa: E402
from custom_components.leelen_home.leelen.common.CommonModel import CommonModel  # noqa: E402
from custom_components.leelen_home.leelen.common.LeelenType import (  # noqa: E402
    FunctionType, GatewayTable,
)
from custom_components.leelen_home.leelen.entity.ack.FetchConfigModAck import FetchConfigModAck  # noqa: E402
from custom_components.leelen_home.leelen.entity.dao.AckToDao import AckToDao  # noqa: E402
from custom_components.leelen_home.leelen.handler import FlowRxBus  # noqa: E402
from custom_components.leelen_home.leelen.handler.DeviceStatusEvent import DeviceStatusEvent  # noqa: E402
from custom_components.leelen_home.leelen.models.DeviceStateModel import DeviceStateModel  # noqa: E402
from custom_components.leelen_home.leelen.models.LanDataRequestModel import LanDataRequestModel  # noqa: E402
from custom_components.leelen_home.leelen.models.MsgStorageModel import MsgStorageModel  # noqa: E402
from custom_components.leelen_home.leelen.states.LinSensorState import LinSensorState  # noqa: E402


# 逻辑地址 33 / 49 / 289 / 353 / 369 为用户真实网关的 5 台智能插座(dump.db 确认)。
SOCKET_A = 33
SOCKET_B = 353


def _b64_counter(value: int) -> str:
    """累计计数 → CSV 里 rec_cont 的 base64(6 字节小端)。"""
    return base64.b64encode(value.to_bytes(6, "little")).decode()


def _mock_config_entry():
    return Mock(entry_id="test", data={})


def _reset_singletons():
    """重置受测单例,避免用例间缓存串扰。"""
    MsgStorageModel.reset_instance()
    CommonModel.reset_instance()
    DeviceStateModel.reset_instance()


# ------------------------------------------------------------------ 纯算法

class TestMsgStorageModel(unittest.TestCase):
    def setUp(self):
        _reset_singletons()
        self.model = MsgStorageModel.get_instance()

    def tearDown(self):
        _reset_singletons()

    def test_six_byte_to_long(self):
        # 官方 sixByteToLong:6 字节低 6 字节,高位 2 字节补 0 → 0x1432
        assert MsgStorageModel.six_byte_to_long(b"\x32\x14\x00\x00\x00\x00") == 0x1432

    def test_six_byte_to_long_empty(self):
        assert MsgStorageModel.six_byte_to_long(b"") == 0
        assert MsgStorageModel.six_byte_to_long(None) == 0

    def test_today_energy_first_vs_last(self):
        # 今日 22556:08:00 起 3 条小时行,首尾累计差。counter 单位 ×0.0001 = kWh。
        base = 10_000_000
        # 3 条今日行,重点在「仅看首尾差」——中间行怎么涨都不影响(12:00 多走的
        # 12_000 不计入,只看 08:00→18:00 的 12_345)。
        self.model.upsert(SOCKET_A, 22556, "2026-09-24 08:00:00", base.to_bytes(6, "little"))
        self.model.upsert(SOCKET_A, 22556, "2026-09-24 12:00:00", (base + 12_000).to_bytes(6, "little"))
        self.model.upsert(SOCKET_A, 22556, "2026-09-24 18:00:00", (base + 12_345).to_bytes(6, "little"))
        # 昨天 23:00 应被「今日 00:00:00」边界过滤掉
        self.model.upsert(SOCKET_A, 22556, "2026-09-23 23:00:00", (0).to_bytes(6, "little"))

        now = datetime(2026, 9, 24, 20, 0, 0)
        # 1.2345 → 3 位 ROUND_HALF_UP → 1.235(不用 Python round 的银行家舍入)
        assert self.model.today_energy(SOCKET_A, now) == 1.235

    def test_today_energy_needs_two_rows(self):
        now = datetime(2026, 9, 24, 20, 0, 0)
        assert self.model.today_energy(SOCKET_A, now) == 0.0
        self.model.upsert(SOCKET_A, 22556, "2026-09-24 08:00:00", (1).to_bytes(6, "little"))
        assert self.model.today_energy(SOCKET_A, now) == 0.0  # 只有 1 行

    def test_today_energy_before_midnight(self):
        # 全部行都在边界之前 → 0
        now = datetime(2026, 9, 24, 1, 0, 0)
        self.model.upsert(SOCKET_A, 22556, "2026-09-23 23:00:00", (1).to_bytes(6, "little"))
        self.model.upsert(SOCKET_A, 22556, "2026-09-23 23:30:00", (2).to_bytes(6, "little"))
        assert self.model.today_energy(SOCKET_A, now) == 0.0

    def test_today_energy_negative_clamped(self):
        # 首行计数 > 末行(网关回拨/脏数据)→ 钳 0
        now = datetime(2026, 9, 24, 20, 0, 0)
        self.model.upsert(SOCKET_A, 22556, "2026-09-24 08:00:00", (5_000_000).to_bytes(6, "little"))
        self.model.upsert(SOCKET_A, 22556, "2026-09-24 09:00:00", (4_000_000).to_bytes(6, "little"))
        assert self.model.today_energy(SOCKET_A, now) == 0.0

    def test_month_energy_day_buckets_with_today_override(self):
        """22557 日计数:每天一对相邻差,当日桶被今日值覆盖,求和 1 位小数。"""
        now = datetime(2026, 9, 24, 20, 0, 0)
        # 9/1 开始每天一条日读数,相邻差恒 100_000 → 每桶 10.0 kWh
        counters = [1_000_000, 1_100_000, 1_200_000, 1_300_000, 1_400_000]
        for day, counter in enumerate(counters, start=1):
            rec_time = f"2026-09-{day:02d} 23:00:00"
            self.model.upsert(SOCKET_A, 22557, rec_time, counter.to_bytes(6, "little"))

        # 今日值(22556)本轮只给两条 → 今日 = (12500-12000)/10000 = 0.05 → 0.050
        self.model.upsert(SOCKET_A, 22556, "2026-09-24 00:30:00", (12_000).to_bytes(6, "little"))
        self.model.upsert(SOCKET_A, 22556, "2026-09-24 22:00:00", (12_500).to_bytes(6, "little"))

        # 桶:9/1..9/4 各 10.0,9/24(今日) = 0.05,合计 40.05 → 1 位小数 = 40.1
        assert self.model.month_energy(SOCKET_A, now) == 40.1

    def test_month_energy_day_multiple_rows_last_pair_wins(self):
        """同一天多行日读数:桶只保留「最后一对相邻差」(官方循环覆盖式)。"""
        now = datetime(2026, 9, 24, 20, 0, 0)
        # 9/1 两行 + 9/2 一行:对 (9/1@08,9/1@22) 差 100_000→10.0,
        # 对 (9/1@22,9/2@08) 差 150_000→15.0 覆盖前值 → 桶=15.0
        self.model.upsert(SOCKET_A, 22557, "2026-09-01 08:00:00", (0).to_bytes(6, "little"))
        self.model.upsert(SOCKET_A, 22557, "2026-09-01 22:00:00", (100_000).to_bytes(6, "little"))
        self.model.upsert(SOCKET_A, 22557, "2026-09-02 08:00:00", (250_000).to_bytes(6, "little"))
        # 今日值 = 0(无 22556 行)
        assert self.model.month_energy(SOCKET_A, now) == 15.0

    def test_month_energy_no_rows(self):
        now = datetime(2026, 9, 24, 20, 0, 0)
        assert self.model.month_energy(SOCKET_A, now) == 0.0

    def test_codes_with_data_and_has_type(self):
        self.model.upsert(SOCKET_A, 22557, "2026-09-02 08:00:00", (1).to_bytes(6, "little"))
        self.model.upsert(SOCKET_B, 22556, "2026-09-24 08:00:00", (1).to_bytes(6, "little"))
        assert self.model.codes_with_data() == [33, 353]
        assert self.model.has_type(SOCKET_A, 22557)
        assert not self.model.has_type(SOCKET_A, 22556)
        assert self.model.has_type(SOCKET_B, 22556)

    def test_upsert_ignores_non_energy_rec_type(self):
        self.model.upsert(SOCKET_A, 9999, "2026-09-24 08:00:00", b"\x01")
        assert self.model.codes_with_data() == []


# ------------------------------------------------------------------ 解析链路

class TestMsgStorageParse(unittest.TestCase):
    def setUp(self):
        _reset_singletons()
        from custom_components.leelen_home.leelen.common.SingletonMixin import SingletonMixin  # noqa: F401

    def tearDown(self):
        _reset_singletons()

    @staticmethod
    def _fetch_ack_for_socket(code: int, rec_type: int, rec_time: str, counter: int) -> FetchConfigModAck:
        header = ("rec_id,rec_set_id,link_target_type,link_target_code,rec_type,"
                  "rec_cont,rec_time,create_time,update_time")
        row = f"1,1,0,{code},{rec_type},{_b64_counter(counter)},{rec_time},0,0"
        return FetchConfigModAck(cont=f"{header}\n{row}", tbl=GatewayTable.MSG_STORAGE_COMMON_TABLE_NAME, type="ins")

    def test_transform_data_merges_and_posts_events(self):
        """AckToDao.transform_data 对 msg_storage_common_tbl:合并缓存 + 每插座 2 个事件。"""
        posted = []

        def _fake_post(event: DeviceStatusEvent):
            posted.append(event)

        with patch.object(FlowRxBus, "post", side_effect=_fake_post):
            AckToDao.get_instance().transform_data(
                self._fetch_ack_for_socket(SOCKET_A, 22556, "2026-09-24 08:00:00", 10_000))
            AckToDao.get_instance().transform_data(
                self._fetch_ack_for_socket(SOCKET_A, 22556, "2026-09-24 09:00:00", 10_500))
            AckToDao.get_instance().transform_data(
                self._fetch_ack_for_socket(SOCKET_A, 22557, "2026-09-02 08:00:00", 100_000))
            # 该插座第一次出现(第二台),也应派发它的事件
            AckToDao.get_instance().transform_data(
                self._fetch_ack_for_socket(SOCKET_B, 22557, "2026-09-03 08:00:00", 1))

        model = MsgStorageModel.get_instance()
        assert model.has_type(SOCKET_A, 22556)
        assert model.has_type(SOCKET_A, 22557)
        assert model.has_type(SOCKET_B, 22557)

        # 只对「有 22556 行」的插座派发 22556/22557 事件;SOCKET_B 只有 22557 → 永不派发。
        # 注意:每个增量 ack 落地后都会对已有小时数据的插座重发一次(实体侧幂等,只是重写
        # 属性)——共 4 次 ack × 2 事件 = 8 条,全指向 SOCKET_A。
        assert len(posted) == 8
        assert {e.logic_address for e in posted} == {SOCKET_A}
        assert {e.function_id for e in posted} == {
            FunctionType.FUNCTION_SMART_SOCKET_HOUR_POWER,
            FunctionType.FUNCTION_SMART_SOCKET_DAY_POWER,
        }
        assert all(e.state == b"" for e in posted)

    def test_transform_data_missing_energy_fields_skips(self):
        """表头缺电能字段(异构表)时优雅跳过,不抛异常。"""
        header = "rec_id,rec_set_id"
        ack = FetchConfigModAck(cont=f"{header}\n1,1", tbl=GatewayTable.MSG_STORAGE_COMMON_TABLE_NAME, type="ins")
        posted = []
        with patch.object(FlowRxBus, "post", side_effect=lambda e: posted.append(e)):
            AckToDao.get_instance().transform_data(ack)
        assert posted == []
        assert MsgStorageModel.get_instance().codes_with_data() == []


# ------------------------------------------------------------------ 状态解析路由

def _frozen_now(cls_at):
    """把被 patch 模块里的 datetime 换成 now() 固定的假时钟。"""

    class _FrozenDatetime:
        fixed = cls_at

        @classmethod
        def now(cls):
            return cls.fixed

    return _FrozenDatetime


class TestCommonModelEnergyBranches(unittest.TestCase):
    def setUp(self):
        _reset_singletons()

    def tearDown(self):
        _reset_singletons()

    def test_get_cur_state_22556_today(self):
        now = datetime(2026, 9, 24, 20, 0, 0)
        model = MsgStorageModel.get_instance()
        model.upsert(SOCKET_A, 22556, "2026-09-24 08:00:00", (9_000_000).to_bytes(6, "little"))
        model.upsert(SOCKET_A, 22556, "2026-09-24 12:00:00", (9_003_333).to_bytes(6, "little"))
        with patch("custom_components.leelen_home.leelen.common.CommonModel.datetime",
                   new=_frozen_now(now)):
            state = CommonModel.get_instance().get_cur_state(
                SOCKET_A, FunctionType.FUNCTION_SMART_SOCKET_HOUR_POWER, b"")
        assert isinstance(state, LinSensorState)
        assert state.get_power() == 0.333  # 3333/10000 = 0.3333 → 3 位 HALF_UP

    def test_get_cur_state_22557_month(self):
        now = datetime(2026, 9, 24, 20, 0, 0)
        model = MsgStorageModel.get_instance()
        model.upsert(SOCKET_A, 22557, "2026-09-02 08:00:00", (100_000).to_bytes(6, "little"))
        model.upsert(SOCKET_A, 22557, "2026-09-03 08:00:00", (125_000).to_bytes(6, "little"))
        # 今日值 0 → 桶 9/2 = 2.5 kWh
        with patch("custom_components.leelen_home.leelen.common.CommonModel.datetime",
                   new=_frozen_now(now)):
            state = CommonModel.get_instance().get_cur_state(
                SOCKET_A, FunctionType.FUNCTION_SMART_SOCKET_DAY_POWER, b"")
        assert isinstance(state, LinSensorState)
        assert state.get_power() == 2.5

    def test_get_cur_state_power_guard_unaffected(self):
        # FUNCTION_POWER(20517) 走原有 get_cur_sensor_power 路径,长 4 字节正常解析
        state = CommonModel.get_instance().get_cur_state(
            SOCKET_A, FunctionType.FUNCTION_POWER, b"\x64\x00\x00\x00")
        assert state.get_power() == 100

    def test_get_cur_state_power_guard_zero_when_short(self):
        stat = CommonModel.get_instance().get_cur_state(
            SOCKET_A, FunctionType.FUNCTION_POWER, b"\x64\x00")
        assert stat.get_power() == 0


# ------------------------------------------------------------ DeviceStateModel

class TestDeviceStatePowerGuard(unittest.TestCase):
    def setUp(self):
        _reset_singletons()

    def tearDown(self):
        _reset_singletons()

    def test_len_four_parsed_little_endian(self):
        model = DeviceStateModel.get_instance()
        assert model.get_power_state(0, 0, b"\x64\x00\x00\x00") == 100
        assert model.get_power_state(0, 0, b"\x2c\x01\x00\x00") == 300  # 0x012c

    def test_wrong_length_returns_zero(self):
        model = DeviceStateModel.get_instance()
        assert model.get_power_state(0, 0, b"\x64") == 0
        assert model.get_power_state(0, 0, b"\x64\x00\x00") == 0
        assert model.get_power_state(0, 0, b"\x64\x00\x00\x00\x00") == 0
        assert model.get_power_state(0, 0, b"") == 0
        assert model.get_power_state(0, 0, None) == 0


# --------------------------------------------------------------------- Switch

class TestSwitchEnergyUpdate(unittest.TestCase):
    def setUp(self):
        _reset_singletons()

    def tearDown(self):
        _reset_singletons()

    def _make_switch(self):
        return Switch(SOCKET_A, "dev1", "插座A", "智能插座设备", _mock_config_entry())

    def test_update_state_power_w(self):
        switch = self._make_switch()
        state = LinSensorState()
        state.set_service_type(FunctionType.FUNCTION_POWER)
        state.set_power(123)  # 原始值 123 → 12.3 W
        with patch.object(switch, "async_write_ha_state", new=Mock()):
            asyncio.run(switch.update_state(state))
        assert switch._power_w == 12.3
        assert switch.extra_state_attributes["current_power_w"] == 12.3  # ×0.1 + 1 位小数

    def test_update_state_today_month(self):
        switch = self._make_switch()
        today_state = LinSensorState()
        today_state.set_service_type(FunctionType.FUNCTION_SMART_SOCKET_HOUR_POWER)
        today_state.set_power(2.3456)
        month_state = LinSensorState()
        month_state.set_service_type(FunctionType.FUNCTION_SMART_SOCKET_DAY_POWER)
        month_state.set_power(10.56)
        with patch.object(switch, "async_write_ha_state", new=Mock()):
            asyncio.run(switch.update_state(today_state))
            asyncio.run(switch.update_state(month_state))
        assert switch._today_energy_kwh == 2.3456
        assert switch._month_energy_kwh == 10.56
        attrs = switch.extra_state_attributes
        assert attrs["today_energy_kwh"] == 2.346  # 3 位
        assert attrs["month_energy_kwh"] == 10.6   # 1 位

    def test_update_state_on_off_untouched_by_energy_events(self):
        switch = self._make_switch()
        # 先收到 off
        off = LinSensorState()
        off.set_service_type(FunctionType.FUNCTION_ON_OFF)
        off.set_power_state(0)
        with patch.object(switch, "async_write_ha_state", new=Mock()):
            asyncio.run(switch.update_state(off))
        assert switch._prop_on is False
        # 后续电能事件不会翻转开关态
        energy = LinSensorState()
        energy.set_service_type(FunctionType.FUNCTION_SMART_SOCKET_HOUR_POWER)
        energy.set_power(1.0)
        with patch.object(switch, "async_write_ha_state", new=Mock()):
            asyncio.run(switch.update_state(energy))
        assert switch._prop_on is False


# ----------------------------------------------------------------- fetch 请求

class TestFetchMsgStorage(unittest.TestCase):
    def setUp(self):
        _reset_singletons()
        LanDataRequestModel.reset_instance()

    def tearDown(self):
        _reset_singletons()
        LanDataRequestModel.reset_instance()

    def test_fetch_msg_storage_data_request(self):
        """fetch_msg_storage_data 请求 msg_storage_common_tbl 全表(type=ins, T2=FF)。"""
        captured = {}

        def _fake_request_config_fetch(fetch_req):
            captured["fetch_req"] = fetch_req

        with patch.object(LanDataRequestModel, "request_config_fetch",
                          side_effect=_fake_request_config_fetch):
            LanDataRequestModel.get_instance().fetch_msg_storage_data(clear_data=True)

        fetch_req = captured["fetch_req"]
        assert fetch_req.tbl == GatewayTable.MSG_STORAGE_COMMON_TABLE_NAME
        assert fetch_req.type == "ins"
        assert fetch_req.num == 100
        assert fetch_req.T1 == 0
        # T2 = FF 全表(小端 8 字节 0xFFFFFFFFFF 前的 4 字节全 FF)

    def test_get_state_data_includes_msg_storage(self):
        """登录后的基线拉取含 msg_storage(否则插座用电量要等轮询才能显示)。"""
        fetched = set()

        def _fake_fetch(tbl_getter, clear_data):
            pass

        with patch.object(LanDataRequestModel, "fetch_device_state_data", new=Mock()) as fd, \
             patch.object(LanDataRequestModel, "fetch_logic_server_state_data", new=Mock()) as fl, \
             patch.object(LanDataRequestModel, "fetch_sensor_state_data", new=Mock()) as fs, \
             patch.object(LanDataRequestModel, "fetch_msg_storage_data",
                          new=Mock(side_effect=lambda clear: fetched.add("msg_storage"))):
            LanDataRequestModel.get_instance().get_state_data()
            assert fd.called and fl.called and fs.called
            assert fetched == {"msg_storage"}


if __name__ == "__main__":
    unittest.main()