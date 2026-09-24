"""button 平台:设备定位 + 窗帘电机方向/重置行程按钮。

三个按钮都是**无状态瞬态动作**,用 HA Button 实体承载最贴切。

- 定位按钮(按设备):``DEVICE_HINT + MODE_FLASH``,让设备指示灯闪约 30 秒。
- 窗帘电机「更改电机方向」「重置行程」(按逻辑通道):经 App 设备透写
  ``WRITE_PRIVATE_PROPERTY``,目标地址是**逻辑通道地址**(电机可写属性 163 挂
  logic_addr,不是 dev_addr)。两个动作共用同一个值字节:bit0=方向(0正/1反),
  bit1=重置行程(置1触发) —— ``改方向→1-direction``,``重置→direction+2``。

协议字节来自对官方 App(com.leelen.luxdomo / com.leelen.community)APK 的逆向:
- cmd = ``PASS_THROUGH_APP_DEVICE`` ([1, 6]),body = [01 TA][len][0x64][01 A3][val_len][val],
  与 Java ``BaseManagerImpl.appDevicePassThrough`` 逐字节一致;
- UI 层 ``GatewayEditCurtainMotorPresenter.updateLogicServiceInfo`` 确认:
  方向点击下发 ``1 ^ mIsReverse``,重置点击下发 ``mIsReverse + 2``。

定位是**设备级**能力,不是属性 136 的能力信号:DEVICE_HINT 直接按物理设备
地址寻址,面板/插座/窗帘等带 LED 的 ZigBee 设备都响应。故判定为「物理设备
(dev_addr≠0)且至少有一个会被建实体的逻辑通道」,与面板指示灯开关的判定
(writable LIGHT_PATTERN)解耦。
"""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity import EntityCategory

from .const import COVER_LOGIC_TYPES, ENTITY_LOGIC_TYPES
from .entity_base import LeelenEntity
from .leelen.common.LeelenType import DeviceMode, PropertyId
from .leelen.models.ControlModel import ControlModel
from .platform_helper import async_setup_entry as _setup_platform


#: 定位按钮 unique_id 前缀。id 直接带设备地址;同步设备清理时若不在白名单
#: 会被误删(config_flow 已登记 leelen_device_locate_{dev_addr})。
DEVICE_LOCATE_UNIQUE_ID_PREFIX = "leelen_device_locate"
#: 窗帘电机「更改方向」按钮 unique_id 前缀,按逻辑通道地址区分。
CURTAIN_MOTOR_DIRECTION_PREFIX = "leelen_curtain_motor_direction"
#: 窗帘电机「重置行程」按钮 unique_id 前缀,按逻辑通道地址区分。
CURTAIN_MOTOR_RESET_PREFIX = "leelen_curtain_motor_reset"
#: property_tbl 里电机方向属性的整数 id(dump.db 实测 163,挂在逻辑地址)。协议
#: 写帧用到的是 ``bytes([1, 163])``(PropertyId.CURTAIN_MOTOR),这里是 DB 匹配用。
_CURTAIN_MOTOR_PROPERTY_ID = 163


def _is_device_locatable(device_info) -> bool:
    """设备是否可定位:物理设备(dev_addr≠0)且至少有一个逻辑通道会被建实体。

    DEVICE_HINT 是设备级指令,按物理地址寻址,不依赖属性 136;插座(518)、
    窗帘、空调等带指示灯的设备都响应。网关(dev_addr==0)自身用「找网关」逻辑,排除。
    """
    dev_addr = device_info.get("dev_addr")
    if dev_addr is None or str(dev_addr) == "0":
        return False
    return any(
        logic_srv.get("logic_type") in ENTITY_LOGIC_TYPES
        for logic_srv in device_info.get("logic_srv", [])
    )


def _curtain_motor_channels(device_info) -> list:
    """返回持可写「电机方向」属性的窗帘逻辑通道列表(门控+初值一起算)。

    电机方向属性 163 挂在**逻辑通道地址**(dev 224 → logic 225,见 query_devices
    的逻辑地址归组),所以判定和建实体都按 logic_srv 来:通道类型在
    COVER_LOGIC_TYPES 且该通道地址上有可写 163 属性,才给这条通道建两个按钮。
    """
    channels = []
    by_addr = {}
    for row in device_info.get("all_property", []):
        if row.get("property_id") == _CURTAIN_MOTOR_PROPERTY_ID and row.get("read_only") == 0:
            by_addr[row.get("addr")] = row
    for logic_srv in device_info.get("logic_srv", []):
        if logic_srv.get("logic_type") in COVER_LOGIC_TYPES:
            row = by_addr.get(logic_srv.get("logic_addr"))
            if row is not None:
                channels.append((logic_srv, row))
    return channels


def _motor_direction_initial(row) -> int:
    """属性 163 现值 → 电机方向初值。LIGHT_PATTERN 的 136 同理,方向属性是
    单字节:0=正转、1=反转(dump.db 实测两电机现值 0)。防御:空/None 按 0。
    """
    val = row.get("val")
    if isinstance(val, (bytes, bytearray)):
        return (val[0] & 1) if val else 0
    if isinstance(val, str) and val.isdigit():
        return int(val) & 1
    return 0


def _build_entities(device_info, config_entry):
    """可定位物理设备 → 定位按钮;每条窗帘电机通道再加方向+重置行程 2 按钮。

    定位按钮按设备建(一个 dev 一个);方向/重置按钮按**逻辑通道**建(一个电机
    通道两个,共享方向状态,重置行程需保留当前方向位)。无窗帘通道时保持返回
    单个定位按钮(与历史行为一致,test_panel_locate 的 isinstance 断言依赖它);
    有窗帘通道时返回 ``[定位, 方向, 重置, ...]`` 列表(platform_helper 两种都吃)。
    """
    locator = None
    # 定位按钮:按物理设备,与属性无关(插座/面板/窗帘都可定位)。
    if _is_device_locatable(device_info):
        locator = DeviceLocateButton(
            device_info.get("dev_addr"),
            device_info.get("dev_name"),
            config_entry)
    # 窗帘电机按钮:按逻辑通道。方向与重置共用 value 字节(bit0 方向,bit1 重置),
    # 故同一通道的两个按钮共享同一份方向状态。
    motor_buttons = []
    for logic_srv, prop_row in _curtain_motor_channels(device_info):
        state = {"direction": _motor_direction_initial(prop_row)}
        motor_buttons.append(CurtainMotorDirectionButton(
            logic_srv.get("logic_addr"),
            logic_srv.get("dev_addr"),
            logic_srv.get("logic_name"),
            device_info.get("dev_name"),
            config_entry, state))
        motor_buttons.append(CurtainMotorResetButton(
            logic_srv.get("logic_addr"),
            logic_srv.get("dev_addr"),
            logic_srv.get("logic_name"),
            device_info.get("dev_name"),
            config_entry, state))
    if not motor_buttons:
        return locator
    entities = [] if locator is None else [locator]
    entities.extend(motor_buttons)
    return entities


async def async_setup_entry(
        hass, config_entry: ConfigEntry, async_add_entities,
) -> None:
    await _setup_platform(hass, config_entry, async_add_entities, _build_entities)


class DeviceLocateButton(LeelenEntity, ButtonEntity):
    """设备定位按钮:press 后发 DEVICE_HINT MODE_FLASH,设备灯闪约 30 秒。

    ``_logic_addr=None``(不订阅状态资源),``device_info`` 归入物理设备
    (与指示灯开关共用 LEELEN_HOME/dev_addr 标识),available
    绑定网关链路。
    """

    #: 归入设备「配置」分组 —— 属临时工具动作,不占主控制区(与指示灯开关一致)。
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, device_id, dev_name: str, config_entry: ConfigEntry):
        super().__init__(None, device_id, dev_name, dev_name, config_entry)

    @property
    def unique_id(self) -> str:
        return f"{DEVICE_LOCATE_UNIQUE_ID_PREFIX}_{self._device_id}"

    @property
    def name(self) -> str:
        return f"{self._device_name} 定位"

    @property
    def icon(self) -> str:
        return "mdi:radar"

    async def async_press(self, **kwargs) -> None:
        """定位按下 → 下发原生 DEVICE_HINT MODE_FLASH,设备指示灯闪约 30 秒。"""
        ControlModel.get_instance().device_hint(self._device_id, DeviceMode.MODE_FLASH)


class CurtainMotorDirectionButton(LeelenEntity, ButtonEntity):
    """更改电机方向按钮:press 后翻转方向位并下发属性写帧。

    值字节 bit0=方向(0正/1反)。按下即发 ``1 - 当前方向`` 的取反值,并把方向
    状态乐观更新 —— 与官方 App ``updateLogicServiceInfo(true)``
    (``1 ^ mIsReverse``)一致。方向初值取设备库属性 163 现值。
    """

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, logic_addr, device_id, name: str, dev_name: str,
                 config_entry: ConfigEntry, state: dict):
        super().__init__(logic_addr, device_id, name, dev_name, config_entry)
        # state 与同通道「重置行程」按钮共享(重置要保留当前方向位)。
        self._state = state

    @property
    def unique_id(self) -> str:
        return f"{CURTAIN_MOTOR_DIRECTION_PREFIX}_{self._logic_addr}"

    @property
    def name(self) -> str:
        return f"{self._name} 更改方向"

    @property
    def icon(self) -> str:
        return "mdi:swap-vertical"

    async def async_press(self, **kwargs) -> None:
        """翻转方向并写属性 163:value = 1 - 当前方向(bit0)。"""
        new_direction = 1 - self._state["direction"]
        ControlModel.get_instance().write_private_property(
            self._logic_addr, PropertyId.CURTAIN_MOTOR, bytes([new_direction]))
        # 乐观更新共享方向状态(重置按钮随后按下时用它保留方向位)。
        self._state["direction"] = new_direction


class CurtainMotorResetButton(LeelenEntity, ButtonEntity):
    """重置行程按钮:press 后下发属性写帧,bit1 置 1 触发行程重置。

    值字节 = ``当前方向 + 2``(bit0 原样保留方向,bit1=2 触发重置) —— 与官方
    App ``updateLogicServiceInfo(false)``(``mIsReverse + 2``)一致。同通道的
    「更改方向」按钮翻转方向后,重置会带上新方向,二者状态通过共享 dict 同步。
    """

    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, logic_addr, device_id, name: str, dev_name: str,
                 config_entry: ConfigEntry, state: dict):
        super().__init__(logic_addr, device_id, name, dev_name, config_entry)
        self._state = state

    @property
    def unique_id(self) -> str:
        return f"{CURTAIN_MOTOR_RESET_PREFIX}_{self._logic_addr}"

    @property
    def name(self) -> str:
        return f"{self._name} 重置行程"

    @property
    def icon(self) -> str:
        return "mdi:restore"

    async def async_press(self, **kwargs) -> None:
        """写属性 163:value = 当前方向 + 2(bit1 触发重置,方向位保持不变)。"""
        ControlModel.get_instance().write_private_property(
            self._logic_addr, PropertyId.CURTAIN_MOTOR,
            bytes([self._state["direction"] + 2]))