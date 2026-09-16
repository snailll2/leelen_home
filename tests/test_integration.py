"""HA 集成级测试 —— 用 pytest-homeassistant-custom-component 在真实 HA 下加载平台并断言实体注册。

在 WSL Docker 容器运行:
    docker exec -e HOME=/tmp ha-test python3 -m pytest /config/tests/test_integration.py -v
"""
import logging
from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant import setup
from homeassistant.helpers import entity_registry as er
from homeassistant.core import HomeAssistant

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.leelen_home.const import DOMAIN, CONF_DEVICE_ADDR, CONF_USERNAME, CONF_PASSWORD
from custom_components.leelen_home.leelen.api.HttpApi import HttpApi
from custom_components.leelen_home.leelen.common.LeelenType import LogicDeviceType
from custom_components.leelen_home.service import LeelenService

_LOGGER = logging.getLogger(__name__)

# 一个带"智能墙面插座"(LogicDeviceType.ZIGBEE_SMART_WALL_SOCKET=518)的假设备
FAKE_DEVICES = [
    {
        "dev_name": "测试墙面插座",
        "dev_addr": "dev_wall_socket_1",
        "logic_srv": [
            {
                "logic_type": LogicDeviceType.ZIGBEE_SMART_WALL_SOCKET,  # 智能墙面插座
                "logic_addr": 1234,
                "dev_addr": "dev_wall_socket_1",
                "logic_name": "TestPlug",
            }
        ],
    },
    {
        "dev_name": "测试窗帘电机",
        "dev_addr": "dev_curtain_1",
        "logic_srv": [
            {
                "logic_type": LogicDeviceType.TYPE_WIRELESS_CURTAIN,  # 无线窗帘
                "logic_addr": 2001,
                "dev_addr": "dev_curtain_1",
                "logic_name": "TestCurtain",
            }
        ],
    },
]


@pytest.mark.asyncio
async def test_setup_registers_entities(
    hass: HomeAssistant,
    enable_custom_integrations,
):
    """加载集成后,应从假设备列表注册出 switch 与 cover 实体。"""
    entry_data = {
        CONF_DEVICE_ADDR: "0123456789abcdef",
        CONF_USERNAME: "u",
        CONF_PASSWORD: "p",
    }

    with (
        patch.object(HttpApi, "refresh_devices", new=AsyncMock(return_value=FAKE_DEVICES)),
        patch.object(HttpApi, "query_gateway_ip", new=AsyncMock(return_value="192.168.1.50")),
        patch.object(LeelenService, "async_start", new=AsyncMock(return_value=None)),
        patch.object(LeelenService, "stop", new=Mock(return_value=None)),
    ):
        entry = MockConfigEntry(domain=DOMAIN, data=entry_data)
        entry.add_to_hass(hass)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    # 通过实体注册表按 unique_id 校验已注册实体
    reg = er.async_get(hass)
    plug_entity = reg.async_get_entity_id("switch", DOMAIN, "leelen_logic_addr_1234")
    assert plug_entity, "应有 switch.TestPlug 实体"
    assert plug_entity.startswith("switch.")
    st = hass.states.get(plug_entity)
    assert st is not None
    # friendly_name = dev_name + " " + logic_name(设备下挂实体) → 设备名"测试墙面插座" + 实体名"TestPlug"
    assert st.attributes.get("friendly_name") == "测试墙面插座 TestPlug"

    # cover: 无线窗帘在 cover.py 注册(LogicDeviceType.TYPE_WIRELESS_CURTAIN=570)
    curtain_entity = reg.async_get_entity_id("cover", DOMAIN, "leelen_logic_addr_2001")
    assert curtain_entity, "应有 cover.TestCurtain 实体"
    assert curtain_entity.startswith("cover.")
    assert hass.states.get(curtain_entity) is not None
