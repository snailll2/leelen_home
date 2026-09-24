"""设备定位按钮测试:DeviceHintLanProtocol 写帧 + DeviceLocateButton 建实体/按下转发。

覆盖:
- ``DeviceHintLanProtocol``:cmd = LAN [5,2],body = [mode][dev_addr 小端 2B]
  —— 用真实 BaseLanProtocol 拼帧,断言 request_data_body = 01 40 00(设备地址 64,FLASH)
- ``DeviceLocateButton.async_press``:按下后经 ControlModel.device_hint 下发 MODE_FLASH
- ``_build_entities``:可定位物理设备(dev_addr≠0 且至少一个实体逻辑通道)
  产出 1 个定位按钮 —— 面板(514)与智能插座(518,无属性 136)都建;
  网关(dev_addr==0)与无实体通道的设备不建
- ``config_flow._collect_expected_unique_ids``:leelen_device_locate_{dev_addr} 进白名单

定位是**设备级**协议原语(官方 App「设备定位」同款),按物理地址寻址,不依赖
属性 136 —— 与面板指示灯开关的「持有可写 136」判定解耦。
"""
import asyncio
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, "/config")

from custom_components.leelen_home.button import (  # noqa: E402
    DEVICE_LOCATE_UNIQUE_ID_PREFIX, DeviceLocateButton, _build_entities,
    _is_device_locatable,
)
from custom_components.leelen_home.config_flow import _collect_expected_unique_ids  # noqa: E402
from custom_components.leelen_home.leelen.common import LanProtocolCmd  # noqa: E402
from custom_components.leelen_home.leelen.common.LeelenType import (  # noqa: E402
    DeviceMode, DeviceType, PropertyId,
)
from custom_components.leelen_home.leelen.models.ControlModel import ControlModel  # noqa: E402

# 面板:逻辑通道 514(灯),持有可写 136 —— 既有「指示灯开关」目标设备。
_PANEL_LOGIC_TYPE = 514
# 智能插座:逻辑通道 518,无属性 136 —— 本次扩展的定位目标。
_SOCKET_LOGIC_TYPE = 518


def _device(dev_addr, logic_type, has_light_property=False):
    all_property = []
    if has_light_property:
        all_property = [{"property_id": PropertyId.LIGHT_PATTERN,
                         "read_only": 0, "val_length": 1, "val": b"\x01"}]
    return {
        "dev_name": f"设备{dev_addr}",
        "dev_addr": dev_addr,
        "logic_srv": [{"logic_type": logic_type, "logic_addr": dev_addr + 1,
                       "logic_name": "通道", "dev_addr": dev_addr}],
        "all_property": all_property,
    }


def _panel_device(dev_addr=64):
    return _device(dev_addr, _PANEL_LOGIC_TYPE, has_light_property=True)


def _socket_device(dev_addr=32):
    return _device(dev_addr, _SOCKET_LOGIC_TYPE)


def _mock_config_entry():
    return Mock(entry_id="test", data={})


# ------------------------------------------------- DeviceHintLanProtocol 写帧

class TestDeviceHintProtocol(unittest.TestCase):
    def test_cmd_is_lan_device_hint(self):
        from custom_components.leelen_home.leelen.protocols.DeviceHintLanProtocol import (
            DeviceHintLanProtocol)
        proto = DeviceHintLanProtocol()
        assert proto.cmd == LanProtocolCmd.DEVICE_HINT == bytes([5, 2])

    def test_body_is_mode_plus_addr_le(self):
        from custom_components.leelen_home.leelen.protocols.DeviceHintLanProtocol import (
            DeviceHintLanProtocol)
        proto = DeviceHintLanProtocol()
        proto.set_hint(DeviceMode.MODE_FLASH, (64).to_bytes(2, "little"))
        proto.build_body()
        # [mode=01][addr=40 00] → 01 40 00
        assert proto.request_data_body == bytes.fromhex("014000"), proto.request_data_body.hex()

    def test_ping_mode_byte_zero(self):
        from custom_components.leelen_home.leelen.protocols.DeviceHintLanProtocol import (
            DeviceHintLanProtocol)
        proto = DeviceHintLanProtocol()
        proto.set_hint(DeviceMode.MODE_PING, (0xFFFF).to_bytes(2, "little"))
        proto.build_body()
        assert proto.request_data_body == bytes.fromhex("00ffff")

    def test_real_frame_head_carries_cmd_0502(self):
        """完整帧构建:头部 cmd 字节(34:36)应为 05 02。"""
        from custom_components.leelen_home.leelen.protocols.DeviceHintLanProtocol import (
            DeviceHintLanProtocol)
        from custom_components.leelen_home.leelen.entity.GatewayInfo import GatewayInfo
        from custom_components.leelen_home.leelen.entity.User import User
        from custom_components.leelen_home.leelen.utils.ConvertUtils import ConvertUtils

        proto = DeviceHintLanProtocol()
        proto.set_hint(DeviceMode.MODE_FLASH, (64).to_bytes(2, "little"))
        frame = proto.get_request_data(
            ConvertUtils.get_long_address_by_type(DeviceType.APP, 1),
            bytes(8), (64).to_bytes(2, "little"))
        # build_body 后 body 已拼进帧,head 中 cmd 位于字节 34..36
        assert frame[34:36] == bytes([5, 2]), frame[:41].hex()


# ------------------------------------------------- 可定位判定

class TestIsDeviceLocatable(unittest.TestCase):
    def test_panel_locatable(self):
        assert _is_device_locatable(_panel_device(dev_addr=64))

    def test_socket_without_light_property_locatable(self):
        """插座没有属性 136,但仍是可定位物理设备。"""
        assert _is_device_locatable(_socket_device(dev_addr=32))

    def test_gateway_dev_addr_zero_not_locatable(self):
        """网关(dev_addr==0)自身用「找网关」逻辑,不建定位按钮。"""
        assert not _is_device_locatable(_device(0, _PANEL_LOGIC_TYPE))

    def test_no_entity_channel_not_locatable(self):
        """逻辑通道不在实体平台接管范围(如冷门保温箱 573)的物理设备不建定位按钮。"""
        dev = _device(128, logic_type=573)
        assert not _is_device_locatable(dev)

    def test_no_logic_srv_not_locatable(self):
        assert not _is_device_locatable({"dev_addr": 128, "logic_srv": [],
                                         "all_property": []})


# ------------------------------------------------- 实体构建 & 按下转发

class TestDeviceLocateButton(unittest.TestCase):
    def test_panel_builds_one_button(self):
        entities = _build_entities(_panel_device(dev_addr=64), _mock_config_entry())
        assert isinstance(entities, DeviceLocateButton), entities
        assert entities.unique_id == f"{DEVICE_LOCATE_UNIQUE_ID_PREFIX}_64"
        assert entities.name == "设备64 定位"
        # Button 平台不使用 is_on(is_on 泄自 LeelenEntity 默认 _prop_on=False,
        # HA 读 state 时调用 ButtonEntity MRO 顶层返回 None)。断言不抛错即可。
        assert entities.entity_category.value == "config"

    def test_socket_builds_one_button(self):
        """插座同样可定位:无属性 136 也建按钮(本轮功能核心)。"""
        entities = _build_entities(_socket_device(dev_addr=32), _mock_config_entry())
        assert isinstance(entities, DeviceLocateButton), entities
        assert entities.unique_id == f"{DEVICE_LOCATE_UNIQUE_ID_PREFIX}_32"
        assert entities.name == "设备32 定位"

    def test_gateway_dev_addr_zero_no_button(self):
        assert _build_entities(_device(0, _PANEL_LOGIC_TYPE), _mock_config_entry()) is None

    def test_no_entity_channel_no_button(self):
        assert _build_entities(_device(128, logic_type=573),
                               _mock_config_entry()) is None

    def test_icon(self):
        sw = _build_entities(_panel_device(), _mock_config_entry())
        assert sw.icon == "mdi:radar"

    def test_press_sends_device_hint_mode_flash(self):
        sw = _build_entities(_panel_device(dev_addr=64), _mock_config_entry())
        captured = {}

        def _fake_device_hint(service_id, mode=DeviceMode.MODE_FLASH):
            captured["service_id"] = service_id
            captured["mode"] = mode

        with patch.object(ControlModel, "device_hint", side_effect=_fake_device_hint):
            asyncio.run(sw.async_press())

        assert captured["service_id"] == 64
        assert captured["mode"] == DeviceMode.MODE_FLASH

    def test_press_for_socket_sends_device_addr(self):
        sw = _build_entities(_socket_device(dev_addr=32), _mock_config_entry())
        captured = {}

        def _fake_device_hint(service_id, mode=DeviceMode.MODE_FLASH):
            captured["service_id"] = service_id

        with patch.object(ControlModel, "device_hint", side_effect=_fake_device_hint):
            asyncio.run(sw.async_press())

        assert captured["service_id"] == 32


# ------------------------------------------------- config_flow 白名单

class TestCollectExpectedUniqueIdsLocate(unittest.TestCase):
    def test_panel_device_adds_locate_id(self):
        got = _collect_expected_unique_ids([_panel_device(dev_addr=64)])
        assert f"{DEVICE_LOCATE_UNIQUE_ID_PREFIX}_64" in got

    def test_socket_device_adds_locate_id(self):
        """插座可定位 → 定位按钮 id 也进清理白名单,防同步误删。"""
        got = _collect_expected_unique_ids([_socket_device(dev_addr=32)])
        assert f"{DEVICE_LOCATE_UNIQUE_ID_PREFIX}_32" in got

    def test_unsupported_channel_device_no_locate_id(self):
        got = _collect_expected_unique_ids([_device(128, logic_type=573)])
        assert not any(uid.startswith(DEVICE_LOCATE_UNIQUE_ID_PREFIX) for uid in got), got

    def test_gateway_no_locate_id(self):
        got = _collect_expected_unique_ids([_device(0, _PANEL_LOGIC_TYPE)])
        assert not any(uid.startswith(DEVICE_LOCATE_UNIQUE_ID_PREFIX) for uid in got), got


if __name__ == "__main__":
    unittest.main()