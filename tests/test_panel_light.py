"""面板指示灯开关测试:PanelIndicatorSwitch 建实体/控制帧 + config_flow 白名单。

覆盖:
- ``_has_writable_panel_light``:设备持有可写属性 136(LIGHT_PATTERN)才建;网关/无属性不建
- ``_build_entities``:面板设备产出 1 个 PanelIndicatorSwitch,unique_id = leelen_panel_light_{dev_addr}
- 初值:属性 136 现值 01→开、00→关、缺失→开(出厂默认)
- ``async_turn_on/off``:经 ControlModel.device_control 发私有属性写帧,负载 = [0x88][01/00]
- 写帧字节:使用真实 TlvUtils/DeviceControlLanProtocol 验证 body = 07400004d25788xx
- ``config_flow._collect_expected_unique_ids``:面板指示灯 id 进清理白名单

运行(在 wsl HA 容器):
    docker exec ha-test python3 -m pytest tests/test_panel_light.py -q
"""
import asyncio
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, "/config")

from homeassistant.helpers.entity import EntityCategory  # noqa: E402

from custom_components.leelen_home.switch import (  # noqa: E402
    PanelIndicatorSwitch, PANEL_LIGHT_UNIQUE_ID_PREFIX, _build_entities,
    _has_writable_panel_light, _panel_light_initial_on,
)
from custom_components.leelen_home.leelen.models.ControlModel import ControlModel  # noqa: E402
from custom_components.leelen_home.config_flow import _collect_expected_unique_ids  # noqa: E402
from custom_components.leelen_home.leelen.common.LeelenType import (  # noqa: E402
    APCIType, PropertyId,
)


def _mock_config_entry():
    return Mock(entry_id="test", data={})


def _panel_device(dev_addr=64, val=b"\x01", read_only=0, extra=None):
    """一层面板设备:属性 136(LIGHT_PATTERN)可写,当前值由 val 决定。"""
    device = {
        "dev_name": f"面板{dev_addr}",
        "dev_addr": dev_addr,
        "logic_srv": [{"logic_type": 514, "logic_addr": dev_addr + 1,
                       "logic_name": "灯", "dev_addr": dev_addr}],
        "all_property": [{"property_id": PropertyId.LIGHT_PATTERN,
                          "read_only": read_only, "val_length": 1, "val": val}],
    }
    if extra:
        device.update(extra)
    return device


def _non_panel_device(dev_addr=32):
    """无 136 属性的普通设备(如插座/窗帘)。"""
    return {
        "dev_name": f"设备{dev_addr}",
        "dev_addr": dev_addr,
        "logic_srv": [{"logic_type": 518, "logic_addr": dev_addr + 1,
                       "logic_name": "插座", "dev_addr": dev_addr}],
        "all_property": [],
    }


# ---------------------------------------------------- 属性 136 判定

class TestHasWritablePanelLight(unittest.TestCase):
    def test_panel_with_writable_136(self):
        assert _has_writable_panel_light(_panel_device(val=b"\x01")) is True

    def test_readonly_136_is_not_writable(self):
        assert _has_writable_panel_light(_panel_device(read_only=1)) is False

    def test_no_property_is_false(self):
        assert _has_writable_panel_light(_non_panel_device()) is False

    def test_gateway_dev_addr_zero_excluded(self):
        # 网关属性实体由 sensor 平台建;开关平台不再给网关建指示灯
        dev = _panel_device(dev_addr=0, val=b"\x01")
        assert _has_writable_panel_light(dev) is False

    def test_all_property_absent_is_safe(self):
        dev = {"dev_name": "x", "dev_addr": 64, "logic_srv": []}
        assert _has_writable_panel_light(dev) is False


# ---------------------------------------------------- 初值解析

class TestPanelLightInitialOn(unittest.TestCase):
    def test_on_byte(self):
        assert _panel_light_initial_on(b"\x01") is True

    def test_off_byte(self):
        assert _panel_light_initial_on(b"\x00") is False

    def test_none_defaults_on(self):
        assert _panel_light_initial_on(None) is True

    def test_empty_defaults_on(self):
        assert _panel_light_initial_on(b"") is True

    def test_digit_string(self):
        assert _panel_light_initial_on("1") is True
        assert _panel_light_initial_on("0") is False


# ---------------------------------------------------- _build_entities

class TestBuildPanelLightEntity(unittest.TestCase):
    def test_panel_builds_one_switch(self):
        entities = _build_entities(_panel_device(val=b"\x01"), _mock_config_entry())
        lights = [e for e in entities if isinstance(e, PanelIndicatorSwitch)]
        assert len(lights) == 1, entities

        sw = lights[0]
        assert sw.unique_id == f"{PANEL_LIGHT_UNIQUE_ID_PREFIX}_64"
        assert sw.name == "面板64 指示灯"
        assert sw.is_on is True
        # 归入设备「配置」分组(纯设置项,不占主控制区)
        assert sw.entity_category == EntityCategory.CONFIG
        assert sw.entity_category is not None

    def test_off_initial_value(self):
        entities = _build_entities(_panel_device(val=b"\x00"), _mock_config_entry())
        sw = next(e for e in entities if isinstance(e, PanelIndicatorSwitch))
        assert sw.is_on is False

    def test_non_panel_device_no_switch(self):
        entities = _build_entities(_non_panel_device(), _mock_config_entry())
        assert not any(isinstance(e, PanelIndicatorSwitch) for e in entities), entities

    def test_readonly_panel_no_switch(self):
        entities = _build_entities(_panel_device(read_only=1), _mock_config_entry())
        assert not any(isinstance(e, PanelIndicatorSwitch) for e in entities), entities

    def test_device_info_grouped_under_device_addr(self):
        entities = _build_entities(_panel_device(), _mock_config_entry())
        sw = next(e for e in entities if isinstance(e, PanelIndicatorSwitch))
        assert sw.device_info["identifiers"] == {("LEELEN_HOME", 64)}
        assert isinstance(sw._device_id, int)  # 保持库内 int 类型(与面板灯同设备)


# ---------------------------------------------------- 控制帧

class TestPanelLightControlFrame(unittest.TestCase):
    def _make_switch(self):
        return PanelIndicatorSwitch(64, "面板64", _mock_config_entry(), initial_on=True)

    def test_turn_on_sends_write_private_property_with_on(self):
        sw = self._make_switch()
        captured = {}

        def _fake_device_control(service_id, control_type, control_data):
            captured["service_id"] = service_id
            captured["control_type"] = control_type
            captured["control_data"] = control_data

        with patch.object(ControlModel, "device_control", side_effect=_fake_device_control) as dc, \
             patch.object(sw, "async_write_ha_state", new=Mock()):
            asyncio.run(sw.async_turn_on())

        assert dc.called
        assert captured["service_id"] == 64            # 设备地址
        assert captured["control_type"] == APCIType.WRITE_PRIVATE_PROPERTY[0]  # 0x64
        assert captured["control_data"] == bytes([PropertyId.LIGHT_PATTERN, 1])  # 88 01
        assert sw.is_on is True

    def test_turn_off_sends_write_private_property_with_off(self):
        sw = self._make_switch()
        captured = {}

        def _fake_device_control(service_id, control_type, control_data):
            captured.update(service_id=service_id, control_type=control_type,
                            control_data=control_data)

        with patch.object(ControlModel, "device_control", side_effect=_fake_device_control), \
             patch.object(sw, "async_write_ha_state", new=Mock()):
            asyncio.run(sw.async_turn_off())

        assert captured["service_id"] == 64
        assert captured["control_type"] == APCIType.WRITE_PRIVATE_PROPERTY[0]
        assert captured["control_data"] == bytes([PropertyId.LIGHT_PATTERN, 0])  # 88 00
        assert sw.is_on is False


# ---------------------------------------------------- 写帧字节(真实编码)

class TestPanelLightWireBytes(unittest.TestCase):
    """用真实 TlvUtils + DeviceControlLanProtocol 复现写帧,钉死字节。

    body = [by2=(n+3)] + service_addr(64→4000) + [by=n] + tlv
    tlv(type=0x64, len=2, val=88xx) → d2 57 88 xx(见 TlvUtils.get_tlv_encode)。
    """

    @staticmethod
    def _body(control_data: bytes) -> bytes:
        from custom_components.leelen_home.leelen.protocols.DeviceControlLanProtocol import (
            DeviceControlLanProtocol)

        from custom_components.leelen_home.leelen.utils.ConvertUtils import ConvertUtils
        from custom_components.leelen_home.leelen.utils.TlvUtils import TlvUtils

        protocol = DeviceControlLanProtocol()
        service_addr = ConvertUtils.short_to_little_byte_array(64)
        protocol.set_service_address(service_addr)
        tlv_info = TlvUtils.get_tlv_encode(
            TlvUtils.tlv_encode([], APCIType.WRITE_PRIVATE_PROPERTY[0],
                                control_data, len(control_data)))
        protocol.set_encode_tlv_info(tlv_info)
        protocol.build_body()
        return protocol.request_data_body

    def test_off_frame_bytes(self):
        body = self._body(bytes([PropertyId.LIGHT_PATTERN, 0]))
        assert body == bytes.fromhex("07400004d2578800"), body.hex()

    def test_on_frame_bytes(self):
        body = self._body(bytes([PropertyId.LIGHT_PATTERN, 1]))
        assert body == bytes.fromhex("07400004d2578801"), body.hex()


# ----------------------------------------------------- config_flow 白名单

class TestCollectExpectedUniqueIdsPanelLight(unittest.TestCase):
    def test_panel_device_adds_panel_light_id(self):
        devices = [_panel_device(dev_addr=64, val=b"\x01")]
        got = _collect_expected_unique_ids(devices)
        assert f"{PANEL_LIGHT_UNIQUE_ID_PREFIX}_64" in got

    def test_non_panel_device_has_no_panel_light_id(self):
        devices = [_non_panel_device(dev_addr=32)]
        got = _collect_expected_unique_ids(devices)
        assert not any(uid.startswith(PANEL_LIGHT_UNIQUE_ID_PREFIX) for uid in got), got

    def test_readonly_panel_no_panel_light_id(self):
        devices = [_panel_device(dev_addr=64, read_only=1)]
        got = _collect_expected_unique_ids(devices)
        assert not any(uid.startswith(PANEL_LIGHT_UNIQUE_ID_PREFIX) for uid in got), got


if __name__ == "__main__":
    unittest.main()