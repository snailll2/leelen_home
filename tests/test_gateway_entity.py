"""网关属性实体 + 软件版本信息 测试。

覆盖(落地 B 之「网关属性实体 + 软件版本」,面板指示灯推迟):
- ``sensor._build_entities``:网关设备(dev_addr==0)展开成属性 sensor(主版本/软件版本/
  IP/MAC/WiFi)+ 在线 binary_sensor;非网关设备不受影响
- ``GatewayAttrSensor``:unique_id `leelen_gateway_attr_*`、native_value 取自 all_property
- ``GatewayOnlineSensor``:is_on = gateway_link_up()
- ``ConvertUtils.decode_soft_version``:7 字节固件版本 → "1.7.1";全 FF/空 → None
- ``entity_base``:device_info.sw_version 注入(供设备注册表「固件」字段)
- ``config_flow._collect_expected_unique_ids``:网关实体进清理白名单

运行(在 wsl HA 容器):
    docker exec ha-test python3 -m pytest tests/test_gateway_entity.py -q
"""
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, "/config")

from custom_components.leelen_home.entity_base import LeelenEntity  # noqa: E402
from custom_components.leelen_home.sensor import (  # noqa: E402
    GatewayAttrSensor, GatewayOnlineSensor, GATEWAY_ATTR_SUFFIXES,
    GATEWAY_ONLINE_UNIQUE_ID, _build_entities,
)
from custom_components.leelen_home.config_flow import _collect_expected_unique_ids  # noqa: E402
from custom_components.leelen_home.leelen.common.LeelenType import PropertyId  # noqa: E402
from custom_components.leelen_home.leelen.utils.ConvertUtils import ConvertUtils  # noqa: E402


def _mock_config_entry():
    return Mock(entry_id="test", data={})


# 网关 addr=0 属性集(示例值,与 _GATEWAY_ATTR_SENSORS 对应;非真实环境数据)
def _gateway_all_property():
    return [
        {"property_id": PropertyId.GW_VER_PROPERTY_ID, "val": "3.12"},
        {"property_id": PropertyId.GW_ADDR_PROPERTY_ID, "val": "192.0.2.135"},
        {"property_id": PropertyId.GW_LITTLE_VER_PROPERTY_ID, "val": "V1.02-181107"},
        {"property_id": PropertyId.GATEWAY_MAC, "val": "AA:BB:CC:DD:EE:FF"},
        {"property_id": PropertyId.WIRELESS_SSID, "val": "Home_WiFi"},
    ]


def _gateway_device_info(addr=0, props=None):
    """网关设备(dev_addr==0)假行:属性可缺省,验证「缺属性不建空实体」。"""
    return {
        "dev_name": "Zigbee无线网关",
        "dev_addr": addr,
        "logic_srv": [{"logic_type": 259, "logic_addr": 4139, "logic_name": "arming"}],
        "all_property": props if props is not None else _gateway_all_property(),
    }


# --------------------------------------------------------- _build_entities 网关分支

class TestBuildGatewayEntities(unittest.TestCase):
    def test_gateway_expands_to_attr_and_online(self):
        entities = _build_entities(_gateway_device_info(), _mock_config_entry())
        attrs = [e for e in entities if isinstance(e, GatewayAttrSensor)]
        online = [e for e in entities if isinstance(e, GatewayOnlineSensor)]
        assert len(attrs) == len(GATEWAY_ATTR_SUFFIXES), entities
        assert len(online) == 1

        by_key = {e._key: e for e in attrs}
        assert set(by_key) == set(GATEWAY_ATTR_SUFFIXES)

        soft = by_key["soft_version"]
        assert soft.unique_id == "leelen_gateway_attr_soft_version"
        assert soft.name == "Zigbee无线网关 软件版本"
        assert soft.native_value == "V1.02-181107"

        ver = by_key["main_version"]
        assert ver.unique_id == "leelen_gateway_attr_main_version"
        assert ver.native_value == "3.12"
        assert ver.name == "Zigbee无线网关 主版本"

        ip = by_key["ip"]
        assert ip.native_value == "192.0.2.135"
        mac = by_key["mac"]
        assert mac.native_value == "AA:BB:CC:DD:EE:FF"
        ssid = by_key["ssid"]
        assert ssid.native_value == "Home_WiFi"

        # 在线实体固定 unique_id,且归入网关同一设备条目(device_id="0")
        assert online[0].unique_id == GATEWAY_ONLINE_UNIQUE_ID
        assert online[0].name == "Zigbee无线网关 在线"
        assert online[0].device_class == "connectivity"

    def test_missing_property_skips_entity(self):
        # 老固件没有 WiFi 属性 → 不建 SSID 传感器,其余照建
        props = [p for p in _gateway_all_property()
                 if p["property_id"] != PropertyId.WIRELESS_SSID]
        entities = _build_entities(_gateway_device_info(props=props), _mock_config_entry())
        assert len(entities) == len(GATEWAY_ATTR_SUFFIXES), entities  # 5 属性 + 1 在线
        assert all(not e.unique_id.startswith("leelen_gateway_attr_ssid")
                   for e in entities)

    def test_online_sensor_is_on_follows_gateway_link(self):
        entities = _build_entities(_gateway_device_info(), _mock_config_entry())
        online = next(e for e in entities if isinstance(e, GatewayOnlineSensor))
        with patch("custom_components.leelen_home.sensor.gateway_link_up",
                   return_value=True):
            assert online.is_on is True
        with patch("custom_components.leelen_home.sensor.gateway_link_up",
                   return_value=False):
            assert online.is_on is False

    def test_non_gateway_device_gets_no_gateway_entities(self):
        # dev_addr != 0:不产出网关实体;空 logic_srv → 普通 sensor 也一个没有
        entities = _build_entities(
            {"dev_name": "面板", "dev_addr": 64, "logic_srv": [], "all_property": []},
            _mock_config_entry())
        assert entities == []


# ------------------------------------------------- ConvertUtils.decode_soft_version

class TestDecodeSoftVersion(unittest.TestCase):
    def test_typical_panel_version(self):
        # dev_tbl.soft_version 7 字节,前 3 字节为主/次/修订
        assert ConvertUtils.decode_soft_version(b"\x01\x07\x01\x00\x00\x00\x00") == "1.7.1"
        assert ConvertUtils.decode_soft_version(b"\x01\x01\x01\x00\x00\x00\x00") == "1.1.1"
        assert ConvertUtils.decode_soft_version(b"\x01\x22\x00\x00\x00\x00\x00") == "1.34.0"

    def test_gateway_unknown_is_none(self):
        # 网关自身 soft_version 全 FF(未上报)→ None,设备注册表不显示固件
        assert ConvertUtils.decode_soft_version(b"\xff\xff\xff\xff\xff\xff\xff") is None

    def test_none_or_short_is_none(self):
        assert ConvertUtils.decode_soft_version(None) is None
        assert ConvertUtils.decode_soft_version(b"") is None
        assert ConvertUtils.decode_soft_version(b"\x01\x07") is None

    def test_str_passthrough(self):
        assert ConvertUtils.decode_soft_version("1.7.1") == "1.7.1"


# ----------------------------------------------------------- device_info.sw_version

class TestDeviceInfoSoftVersion(unittest.TestCase):
    def test_sw_version_injected_shows_in_device_info(self):
        ent = LeelenEntity(1234, "32", "Test", "面板32", _mock_config_entry())
        assert ent.device_info["sw_version"] is None  # 未注入 → 省略(HA 不落字段)
        ent._soft_version = "1.7.1"
        assert ent.device_info["sw_version"] == "1.7.1"

    def test_gateway_attr_sensor_grouped_under_gateway_device(self):
        # device_id 保持库内 int 类型(与 VSwitch 等平台同设备,杜绝「两个网关」)
        entities = _build_entities(_gateway_device_info(), _mock_config_entry())
        ent = entities[0]
        assert isinstance(ent._device_id, int)
        assert ent.device_info["identifiers"] == {("LEELEN_HOME", 0)}


# ----------------------------------------------------- config_flow 清理白名单

class TestCollectExpectedUniqueIdsGateway(unittest.TestCase):
    def test_gateway_device_adds_gateway_ids(self):
        devices = [
            {"dev_addr": 0, "logic_srv": [
                {"logic_type": 259, "logic_addr": 4139, "logic_name": "arming"},
            ]},
            {"dev_addr": 64, "logic_srv": [
                {"logic_type": 513, "logic_addr": 70, "logic_name": "L"},
            ]},
        ]
        got = _collect_expected_unique_ids(devices)
        assert GATEWAY_ONLINE_UNIQUE_ID in got
        for suffix in GATEWAY_ATTR_SUFFIXES:
            assert f"leelen_gateway_attr_{suffix}" in got, suffix
        # 非网关设备不产生网关 id
        assert got == ({"leelen_logic_addr_4139", "leelen_logic_addr_70"}
                       | {GATEWAY_ONLINE_UNIQUE_ID}
                       | {f"leelen_gateway_attr_{s}" for s in GATEWAY_ATTR_SUFFIXES})

    def test_no_gateway_device_no_gateway_ids(self):
        devices = [{"dev_addr": 64, "logic_srv": [
            {"logic_type": 513, "logic_addr": 70, "logic_name": "L"},
        ]}]
        got = _collect_expected_unique_ids(devices)
        assert GATEWAY_ONLINE_UNIQUE_ID not in got
        assert all(f"leelen_gateway_attr_{s}" not in got for s in GATEWAY_ATTR_SUFFIXES)


if __name__ == "__main__":
    unittest.main()