"""HA 集成级测试 —— 用 pytest-homeassistant-custom-component 在真实 HA 下加载平台并断言实体注册。

在 WSL Docker 容器运行:
    docker exec -e HOME=/tmp ha-test python3 -m pytest /config/tests/test_integration.py -v
"""
import logging
from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant import data_entry_flow
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.core import HomeAssistant

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.leelen_home import climate as climate_platform
from custom_components.leelen_home import sensor as sensor_platform
from custom_components.leelen_home.const import (DOMAIN, CONF_DEVICE_ADDR, CONF_USERNAME,
                                                 CONF_PASSWORD, ENTITY_LOGIC_TYPES,
                                                 SENSOR_LOGIC_TYPES, CLIMATE_LOGIC_TYPES,
                                                 COVER_LOGIC_TYPES, LIGHT_LOGIC_TYPES,
                                                 SOCKET_LOGIC_TYPES, CONNECT_MODE_LAN)
from custom_components.leelen_home.state_subscription import SIGNAL_AVAILABILITY_UPDATE
from custom_components.leelen_home.leelen.api.HttpApi import HttpApi
from custom_components.leelen_home.leelen.common.LeelenType import LogicDeviceType
from custom_components.leelen_home.leelen.entity.GatewayInfo import GatewayInfo
from custom_components.leelen_home.leelen.HeartbeatService import HeartbeatService
from custom_components.leelen_home.service import LeelenService

_LOGGER = logging.getLogger(__name__)


def _install_lan_link(logged_on: bool):
    """把 HeartbeatService 的 LAN 连接置为替身,控制实体 available 的判据。

    实体在链路未登录时会写 unavailable(这是刻意行为),所以要断言实体状态值的用例
    必须先让链路处于「已登录」。反之传 False 可复现断线。
    """
    hs = HeartbeatService.get_instance()
    hs.request_mode = CONNECT_MODE_LAN
    if not logged_on:
        hs.connect_lan = None
        return None
    conn = Mock()
    conn.is_logged_on = Mock(return_value=True)
    hs.connect_lan = conn
    return conn

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

    # 实体在链路未登录时写 unavailable,断言状态前先让链路「已登录」
    _install_lan_link(logged_on=True)
    with (
        patch.object(HttpApi, "refresh_devices", new=AsyncMock(return_value=FAKE_DEVICES)),
        patch.object(HttpApi, "query_gateway_ip", new=AsyncMock(return_value="192.0.2.50")),
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

    # 插座(518):sensor 平台为每台插座额外建 3 个电参数传感器 —— 后缀 unique_id,
    # 与 switch 平台的 Switch(裸 ID)并存,页面可直接看到 sensor.<插座>_当前功率 等。
    # (断言按 unique_id 查注册表;entity_id 由 HA 从显示名转写,不硬编码。)
    for missing_uid in (
        "leelen_logic_addr_1234_current_power_w",
        "leelen_logic_addr_1234_today_energy_kwh",
        "leelen_logic_addr_1234_month_energy_kwh",
    ):
        socket_sensor_id = reg.async_get_entity_id("sensor", DOMAIN, missing_uid)
        assert socket_sensor_id, f"应有 sensor 实体 (unique_id={missing_uid})"
        assert socket_sensor_id.startswith("sensor.")
        assert hass.states.get(socket_sensor_id) is not None


@pytest.mark.asyncio
async def test_gateway_entities_registered(
    hass: HomeAssistant,
    enable_custom_integrations,
):
    """网关(dev_addr==0)应注册属性 sensor 与在线 binary_sensor;面板设备固件版本
    应写入设备注册表 sw_version(「固件」字段)。"""
    entry_data = {
        CONF_DEVICE_ADDR: "0123456789abcdef",
        CONF_USERNAME: "u",
        CONF_PASSWORD: "p",
    }
    gateway_dev = {
        "dev_name": "Zigbee无线网关",
        "dev_addr": 0,
        "logic_srv": [],  # 网关的 ARM 通道交给 switch 平台,这里只测 sensor 分支
        "all_property": [
            {"property_id": 0, "val": "3.12"},
            {"property_id": 1, "val": "192.0.2.135"},
            {"property_id": 2, "val": "V1.02-181107"},
            {"property_id": 164, "val": "AA:BB:CC:DD:EE:FF"},
            {"property_id": 165, "val": "Home_WiFi"},
        ],
        "soft_version": None,  # 网关自身固件列全 FF(未上报)→ 注册表不显示
    }
    panel_dev = {
        "dev_name": "面板64",
        "dev_addr": 64,
        "logic_srv": [{"logic_type": LogicDeviceType.TYPE_WIRELESS_LIGHT,
                       "logic_addr": 65, "dev_addr": 64, "logic_name": "灯65"}],
        "all_property": [],
        "soft_version": "1.7.1",
    }

    _install_lan_link(logged_on=True)  # 网关在线,在线实体才显示 on
    with (
        patch.object(HttpApi, "refresh_devices",
                     new=AsyncMock(return_value=[gateway_dev, panel_dev])),
        patch.object(HttpApi, "query_gateway_ip", new=AsyncMock(return_value="192.0.2.50")),
        patch.object(LeelenService, "async_start", new=AsyncMock(return_value=None)),
        patch.object(LeelenService, "stop", new=Mock(return_value=None)),
    ):
        entry = MockConfigEntry(domain=DOMAIN, data=entry_data)
        entry.add_to_hass(hass)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    reg = er.async_get(hass)

    # 5 个网关属性 sensor + 1 个在线 binary_sensor —— 均挂在 sensor 平台
    # (HA 平台域决定 entity_id 前缀;门磁/水浸等 BinarySensor 同样是 sensor.*,
    #  在线实体与它们一致,is_on 仍由 BinarySensorEntity 提供 "on"/"off")。
    expected = [
        ("sensor", "leelen_gateway_attr_main_version", "3.12"),
        ("sensor", "leelen_gateway_attr_soft_version", "V1.02-181107"),
        ("sensor", "leelen_gateway_attr_ip", "192.0.2.135"),
        ("sensor", "leelen_gateway_attr_mac", "AA:BB:CC:DD:EE:FF"),
        ("sensor", "leelen_gateway_attr_ssid", "Home_WiFi"),
        ("sensor", "leelen_gateway_online", "on"),
    ]
    for platform, uid, value in expected:
        entity_id = reg.async_get_entity_id(platform, DOMAIN, uid)
        assert entity_id, f"应有 {platform} 实体 (unique_id={uid})"
        state = hass.states.get(entity_id)
        assert state is not None, f"{uid} 应有状态"
        assert state.state == value, f"{uid} 应为 {value!r},实际 {state.state!r}"

    # 在线实体归入网关设备(identifier ("LEELEN_HOME", 0)—— int,与 switch 平台
    # VSwitch 同标识,才不会被设备注册表当成两台「Zigbee无线网关」)。
    online_id = reg.async_get_entity_id("sensor", DOMAIN, "leelen_gateway_online")
    dev = _get_device_by_identifier(dr.async_get(hass), ("LEELEN_HOME", 0))
    assert dev is not None, "网关 device registry 条目应存在"

    # 面板设备固件版本写入注册表「固件」字段
    panel_dev_rec = _get_device_by_identifier(dr.async_get(hass), ("LEELEN_HOME", 64))
    assert panel_dev_rec is not None
    assert panel_dev_rec.sw_version == "1.7.1", (
        f"设备注册表应显示固件 1.7.1,实际 {panel_dev_rec.sw_version}")
    # 网关固件未上报 → 注册表不显示固件
    assert dev.sw_version in (None, ""), f"网关固件未上报,不应有版本。实际 {dev.sw_version}"


def _get_device_by_identifier(registry, identifier):
    """按 (domain, id) 在设备注册表中取设备(新版 API,避开已废弃的 devices/.async_get_device)。

    identifier 各段须与实体注入注册表时类型一致(网关/面板 dev_addr 是库内 int);
    类型不一致会导致查不到 —— 这恰恰是「两台 Zigbee无线网关」的成因,守在这里。
    """
    for dev in registry.async_get_devices(identifiers={identifier}):
        if identifier in dev.identifiers:
            return dev
    return None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("configured_ip", "dump_ip", "expected"),
    [
        # 配置了网关 IP → 用它,且不去读 dump.db(dump 值不可信才是这个选项存在的理由)
        ("10.0.0.9", "192.0.2.190", "10.0.0.9"),
        # 未配置 → 回落到 dump.db 自动检测值
        ("", "192.0.2.190", "192.0.2.190"),
    ],
)
async def test_gateway_ip_source_precedence(
    hass: HomeAssistant,
    enable_custom_integrations,
    configured_ip,
    dump_ip,
    expected,
):
    """网关 IP 来源由「是否配置」决定,并一路生效到连接层用的 GatewayInfo。"""
    GatewayInfo.reset_instance()
    dump_query = AsyncMock(return_value=dump_ip)
    options = {"config": {"gateway_ip": configured_ip}} if configured_ip else {}

    with (
        patch.object(HttpApi, "refresh_devices", new=AsyncMock(return_value=[])),
        patch.object(HttpApi, "query_gateway_ip", new=dump_query),
        # 只拦掉真正的 socket 连接与状态监控,让 async_start 的其余逻辑(含
        # GatewayInfo 赋值)真实执行 —— 那才是 ConnectLan 实际取地址的地方。
        # LAN 启动自检(49153 TCP 探测)同样会碰 socket,统一 mock 成可达。
        patch.object(HeartbeatService, "lan_conn_create", new=Mock(return_value=None)),
        patch.object(HeartbeatService, "wan_conn_open", new=Mock(return_value=None)),
        patch.object(LeelenService, "_probe_lan", new=AsyncMock(return_value=True)),
        patch.object(LeelenService, "_start_connection_monitor", new=Mock(return_value=None)),
    ):
        entry = MockConfigEntry(domain=DOMAIN, options=options, data={
            CONF_DEVICE_ADDR: "gw1", CONF_USERNAME: "u", CONF_PASSWORD: "p"})
        entry.add_to_hass(hass)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        stored = hass.data[DOMAIN][entry.entry_id]["gateway_ip"]
        assert stored == expected, f"hass.data 应存 {expected},实际 {stored}"
        # ConnectLan.connect_lan() 取的就是这个字段
        assert GatewayInfo.get_instance().lan_address_ip == expected, (
            f"连接层应使用 {expected},实际 {GatewayInfo.get_instance().lan_address_ip}")

        if configured_ip:
            assert not dump_query.called, "已配置网关 IP 时不应再读 dump.db"
        else:
            assert dump_query.called, "未配置时应回落读 dump.db"

        await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
    GatewayInfo.reset_instance()


@pytest.mark.asyncio
async def test_setup_creates_entities_that_registry_already_knows(
    hass: HomeAssistant,
    enable_custom_integrations,
):
    """重启场景:注册表里已有上次运行留下的实体,setup 仍须真正把它们建出来。

    实体注册表跨重启持久化。device_refresh 的「跳过已添加实体」逻辑若以注册表为准,
    启动时会把所有实体都当成已存在而跳过 —— 平台一个实体都不提供,HA 便把注册表里
    的实体恢复成 unavailable(真机上表现为「实体全部不可用」)。
    因此只能以「本次运行已添加过谁」为准,本用例守住这一点。
    """
    registry = er.async_get(hass)
    _install_lan_link(logged_on=True)  # 链路已登录,实体才会写到真实状态
    entry = MockConfigEntry(domain=DOMAIN, data={
        CONF_DEVICE_ADDR: "gw1", CONF_USERNAME: "u", CONF_PASSWORD: "p"})
    entry.add_to_hass(hass)
    # 模拟上次运行留下的注册表条目:必须绑定到同一个 config entry,
    # 否则「按 config entry 取注册表」的过滤逻辑看不到它,复现不出问题。
    registry.async_get_or_create("switch", DOMAIN, "leelen_logic_addr_1234",
                                 config_entry=entry,
                                 suggested_object_id="test_plug")

    with (
        patch.object(HttpApi, "refresh_devices", new=AsyncMock(return_value=FAKE_DEVICES)),
        patch.object(HttpApi, "query_gateway_ip", new=AsyncMock(return_value="192.0.2.50")),
        patch.object(LeelenService, "async_start", new=AsyncMock(return_value=None)),
        patch.object(LeelenService, "stop", new=Mock(return_value=None)),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        entity_id = registry.async_get_entity_id("switch", DOMAIN, "leelen_logic_addr_1234")
        assert entity_id, "实体应已注册"
        state = hass.states.get(entity_id)
        assert state is not None, "注册表里已有该实体时,平台仍必须提供实体(否则会显示不可用)"
        assert state.state == "off", f"实体应处于真实状态,实际: {state.state}"

        await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()


def test_platform_type_sets_match_builders():
    """const 里的 logic_type 集合必须与各平台 _build_entities 的判定一致。

    这些集合被「同步设备」用来判断一台设备是否会出现在设备注册表里;
    若某平台改了判定而没同步 const,统计会再次开始说谎(见 test_refresh_stats_no_phantom_added)。
    """
    assert climate_platform.SUPPORTED_LOGIC_TYPES == CLIMATE_LOGIC_TYPES
    assert set(sensor_platform._SENSOR_SPECS) == SENSOR_LOGIC_TYPES
    # cover/light/socket 的判定直接引用 const,这里守住它们的取值没被改错
    assert COVER_LOGIC_TYPES == {LogicDeviceType.TYPE_WIRELESS_CURTAIN}
    assert LIGHT_LOGIC_TYPES == {LogicDeviceType.TYPE_WIRELESS_LIGHT}
    assert SOCKET_LOGIC_TYPES == {LogicDeviceType.ZIGBEE_SMART_WALL_SOCKET,
                                  LogicDeviceType.WIRELESS_DOUBLE_CURTAIN_PANEL}
    # 全集必须覆盖各平台,否则设备会被错判为「无可控通道」
    for subset in (CLIMATE_LOGIC_TYPES, COVER_LOGIC_TYPES, LIGHT_LOGIC_TYPES,
                   SENSOR_LOGIC_TYPES, SOCKET_LOGIC_TYPES):
        assert subset <= ENTITY_LOGIC_TYPES


@pytest.mark.asyncio
async def test_refresh_stats_no_phantom_added(
    hass: HomeAssistant,
    enable_custom_integrations,
    caplog,
):
    """同步统计:无可控通道的设备不得每轮都算作「新增」,且重复同步不刷重复实体。

    复现真机场景:设备库里有一台双路窗帘面板,其逻辑通道 srv_type=0(被
    query_devices 的过滤条件丢掉),因此永远建不出实体、永远没有设备注册表条目。
    旧口径拿全量 dev_tbl 去比注册表,这台设备每轮都显示为「新增 1 台」。
    """
    socket_dev = {
        "dev_name": "测试墙面插座",
        "dev_addr": 32,
        "logic_srv": [{"logic_type": LogicDeviceType.ZIGBEE_SMART_WALL_SOCKET,
                       "logic_addr": 1234, "dev_addr": 32, "logic_name": "TestPlug",
                       "srv_type": 1}],
    }
    # 无可用逻辑通道(等价于 srv_type 全被过滤):永远不建实体
    no_channel_dev = {"dev_name": "ZigBee 双路窗帘控制面板208", "dev_addr": 208,
                      "logic_srv": []}
    # 同步中途才出现的新设备
    new_light_dev = {
        "dev_name": "新加的灯",
        "dev_addr": 48,
        "logic_srv": [{"logic_type": LogicDeviceType.TYPE_WIRELESS_LIGHT,
                       "logic_addr": 4800, "dev_addr": 48, "logic_name": "NewLight",
                       "srv_type": 1}],
    }

    async def _refresh(hass, entry, devices):
        """跑一次「同步设备」,返回结果页的 description_placeholders。"""
        with patch.object(HttpApi, "refresh_devices", new=AsyncMock(return_value=devices)):
            result = await hass.config_entries.options.async_init(entry.entry_id)
            result = await hass.config_entries.options.async_configure(
                result["flow_id"], user_input={"next_step_id": "refresh"})
            assert result["type"] == data_entry_flow.FlowResultType.FORM, result
            await hass.async_block_till_done()  # 让 device_refresh 分发落地
            return result["description_placeholders"]

    with (
        patch.object(HttpApi, "refresh_devices",
                     new=AsyncMock(return_value=[socket_dev, no_channel_dev])),
        patch.object(HttpApi, "query_gateway_ip", new=AsyncMock(return_value="192.0.2.50")),
        patch.object(LeelenService, "async_start", new=AsyncMock(return_value=None)),
        patch.object(LeelenService, "stop", new=Mock(return_value=None)),
    ):
        entry = MockConfigEntry(domain=DOMAIN, data={
            CONF_DEVICE_ADDR: "gw1", CONF_USERNAME: "u", CONF_PASSWORD: "p"})
        entry.add_to_hass(hass)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        # setup 阶段插座已建实体并注册;窗帘面板无通道 → 只能算「无可控通道」
        stats = await _refresh(hass, entry, [socket_dev, no_channel_dev])
        _LOGGER.warning("同步#1: %s", stats)
        assert stats["total"] == "2"
        assert stats["added"] == "0", f"没有新设备,不应有新增。实际: {stats}"
        assert stats["no_channel"] == "1", f"窗帘面板应计为无可控通道。实际: {stats}"

        # 设备库真出现新设备:应如实算 1 台新增
        stats = await _refresh(hass, entry, [socket_dev, no_channel_dev, new_light_dev])
        _LOGGER.warning("同步#2: %s", stats)
        assert stats["total"] == "3"
        assert stats["added"] == "1", f"新灯应计为新增。实际: {stats}"
        assert stats["no_channel"] == "1"
        assert er.async_get(hass).async_get_entity_id(
            "light", DOMAIN, "leelen_logic_addr_4800"), "新灯的实体应已建立"

        # 回归点:再同步一次必须归零(旧口径这里永远显示 1 台)
        stats = await _refresh(hass, entry, [socket_dev, no_channel_dev, new_light_dev])
        _LOGGER.warning("同步#3: %s", stats)
        assert stats["added"] == "0", f"重复同步不应再有新增。实际: {stats}"
        assert stats["no_channel"] == "1"

    # refresh 重跑时不应为已存在实体刷 unique_id 重复的 ERROR
    dup_errors = [r for r in caplog.records
                  if r.levelno >= logging.ERROR and "unique IDs" in r.getMessage()]
    assert not dup_errors, f"重复实体不应报错: {[r.getMessage() for r in dup_errors]}"

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


@pytest.mark.asyncio
async def test_entities_unavailable_when_link_down_then_recover(
    hass: HomeAssistant,
    enable_custom_integrations,
):
    """链路未登录时实体应为 unavailable,链路恢复后自动回到真实状态。

    实体状态全部来自网关链路推送;此前实体从不实现 available,断线后界面仍显示最后
    一次收到的旧值(看起来还能控制)。这里守住两条:断线→不可用,以及
    service.py 广播可用性信号后实体自行恢复。
    """
    from homeassistant.helpers.dispatcher import async_dispatcher_send

    # 先按「链路未登录」启动
    _install_lan_link(logged_on=False)
    with (
        patch.object(HttpApi, "refresh_devices", new=AsyncMock(return_value=FAKE_DEVICES)),
        patch.object(HttpApi, "query_gateway_ip", new=AsyncMock(return_value="192.0.2.50")),
        patch.object(LeelenService, "async_start", new=AsyncMock(return_value=None)),
        patch.object(LeelenService, "stop", new=Mock(return_value=None)),
    ):
        entry = MockConfigEntry(domain=DOMAIN, data={
            CONF_DEVICE_ADDR: "gw1", CONF_USERNAME: "u", CONF_PASSWORD: "p"})
        entry.add_to_hass(hass)
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        entity_id = er.async_get(hass).async_get_entity_id(
            "switch", DOMAIN, "leelen_logic_addr_1234")
        assert entity_id, "实体应已注册"
        assert hass.states.get(entity_id).state == "unavailable", \
            "链路未登录时实体应不可用(而非显示旧值)"

        # 链路恢复 → 连接监控广播可用性信号 → 实体写状态
        _install_lan_link(logged_on=True)
        async_dispatcher_send(hass, SIGNAL_AVAILABILITY_UPDATE)
        await hass.async_block_till_done()
        assert hass.states.get(entity_id).state == "off", \
            "链路恢复后实体应回到真实状态"

        # 再断线 → 回到不可用
        _install_lan_link(logged_on=False)
        async_dispatcher_send(hass, SIGNAL_AVAILABILITY_UPDATE)
        await hass.async_block_till_done()
        assert hass.states.get(entity_id).state == "unavailable"

        await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
