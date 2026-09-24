"""Constants for the leelen integration."""
from typing import Final

from homeassistant.components.climate import HVACMode, FAN_AUTO, FAN_LOW, FAN_HIGH, FAN_MEDIUM

from .leelen.common.LeelenType import LogicDeviceType

DOMAIN: Final = "leelen"

SUPPORTED_PLATFORMS: list = [
    # 'binary_sensor',
    'button',  # 设备定位按钮(DeviceHint MODE_FLASH)
    'climate',
    'cover',
    # 'event',
    # 'fan',
    # 'humidifier',
    'light',
    # 'notify',
    # 'number',
    # 'select',
    'sensor',
    'switch',
    # 'text',
    # 'vacuum',
    # 'water_heater',
]

# #### Config ####
CONF_PHONE: Final = "phone"
CONF_USERNAME: Final = "username"
CONF_PASSWORD: Final = "password"
CONF_DEVICE_ADDR: Final = "deviceAddr"
CONF_ACCOUNT_ID: Final = "accountId"
CONF_GATEWAY_IP: Final = "gateway_ip"
CONF_CONNECT_MODE: Final = "connect_mode"

CONNECT_MODE_LAN: Final = "lan"
CONNECT_MODE_WAN: Final = "wan"
DEFAULT_CONNECT_MODE: Final = CONNECT_MODE_LAN

OPTIONS_CONFIG: Final = "config"
OPTIONS_SELECT: Final = "select"
OPTIONS_LINKED_ENTITIES: Final = "linked_entities"

# #### 平台接管的 logic_type(单一事实来源) ####
# 各平台 _build_entities 的判定与「同步设备」的统计口径都引用这里,避免两处列表漂移。
# 注意:text 平台未列入 SUPPORTED_PLATFORMS,故 property_* 不参与判定。
# 气候按逻辑类型(而非 dev_name/固定地址)三分类 —— 不针对任何具体房间设计。
AC_LOGIC_TYPES: Final = frozenset({
    LogicDeviceType.TYPE_CENTER_AIR_CONDITIONER,           # 146 中心空调
    LogicDeviceType.ZIGBEE_CENTER_AC,                      # 658 中心空调(ZigBee)
    LogicDeviceType.TYPE_AC_CONTROL,                       # 770 中心空调控制
    LogicDeviceType.TYPE_AC_ACTUATOR,                      # 773 空调执行器
    LogicDeviceType.DIY_CENTER_AC,                         # 778 DIY 中心空调
    LogicDeviceType.ZIGBEE_AC_GATEWAY_AC,                  # 782 ZigBee AC 网关(空调侧)
    LogicDeviceType.TYPE_INFRARED_AC,                      # 242 红外空调
    LogicDeviceType.TYPE_KTV_485_CENTER_AIR_CONDITIONER,   # 157 KTV 485 中心空调
})
FRESH_AIR_LOGIC_TYPES: Final = frozenset({
    LogicDeviceType.TYPE_FRESH_CONTROL,                    # 771 新风控制
    LogicDeviceType.TYPE_FRESH_ACTUATOR,                   # 774 新风执行器
    LogicDeviceType.TYPE_AC_FRESH,                         # 777 空调新风
    LogicDeviceType.DIY_REFRESH_AIR,                       # 780 DIY 新风
    LogicDeviceType.ZIGBEE_AC_GATEWAY_REFRESH_AIR,         # 783 ZigBee AC 网关(新风侧)
    LogicDeviceType.TYPE_REFRESH_AIR,                      # 152 新风
    LogicDeviceType.TYPE_VENTILATION_SYSTEM,               # 148 通风系统
    LogicDeviceType.ZIGBEE_REFRESH_AIR,                    # 664 ZigBee 新风
})
FLOOR_HEATING_LOGIC_TYPES: Final = frozenset({
    LogicDeviceType.TYPE_FLOOR_CONTROL,                    # 772 地板加热器控制
    LogicDeviceType.TYPE_FLOOR_ACTUATOR,                   # 775 地暖执行器
    LogicDeviceType.TYPE_FLOOR,                            # 776 地板加热器
    LogicDeviceType.DIY_FLOOR_HEARTING,                    # 779 DIY 地暖
    LogicDeviceType.TYPE_FLOOR_HEATING_NEW,                # 150 地板加热器(新)
    LogicDeviceType.ZIGBEE_FLOOR_HEARTING,                 # 662 ZigBee 地暖
})
CLIMATE_LOGIC_TYPES: Final = (
    AC_LOGIC_TYPES | FRESH_AIR_LOGIC_TYPES | FLOOR_HEATING_LOGIC_TYPES
)
COVER_LOGIC_TYPES: Final = frozenset({LogicDeviceType.TYPE_WIRELESS_CURTAIN})
LIGHT_LOGIC_TYPES: Final = frozenset({LogicDeviceType.TYPE_WIRELESS_LIGHT})
SENSOR_LOGIC_TYPES: Final = frozenset({
    LogicDeviceType.TYPE_TEMPERATURE_SENSOR,
    LogicDeviceType.TYPE_PM_SENSOR,
    LogicDeviceType.TYPE_HUMIDITY_SENSOR,
    LogicDeviceType.TYPE_WIRELESS_DOOR_SENSOR,
    LogicDeviceType.TYPE_WIRELESS_WATER_IMMERSION_SENSOR,
    # 智能插座(518):sensor 平台会为每个此类通道建 3 个电参数传感器
    # (功率/今日用电/本月用电),与 switch 平台的 Switch 实体并存。
    LogicDeviceType.ZIGBEE_SMART_WALL_SOCKET,
})
#: switch 平台下建 Switch(智能插座)实体的 logic_type。
SOCKET_LOGIC_TYPES: Final = frozenset({
    LogicDeviceType.ZIGBEE_SMART_WALL_SOCKET,
    # 572:旧代码以裸数字当作插座位匹配;实测该通道 srv_type=0,会被设备查询过滤。
    LogicDeviceType.WIRELESS_DOUBLE_CURTAIN_PANEL,
})
#: switch 平台接管的全部 logic_type(插座 + V设备)。
SWITCH_LOGIC_TYPES: Final = SOCKET_LOGIC_TYPES | {LogicDeviceType.ARM}

#: 会被某个已启用平台建出实体的 logic_type 全集。
#: 用于判断一台设备是否会出现在 HA 设备注册表里(无实体=无注册表条目)。
ENTITY_LOGIC_TYPES: Final = (
    CLIMATE_LOGIC_TYPES | COVER_LOGIC_TYPES | LIGHT_LOGIC_TYPES
    | SENSOR_LOGIC_TYPES | SWITCH_LOGIC_TYPES
)

# #### 设备协议常量 ####
# 灯/插座/空调等开关型设备的 power_state 取值:
# 0=关, 1=开, 3=开并携带模式/温度等设定值(与关机设定区分)。
POWER_OFF: Final = 0
POWER_ON: Final = 1
POWER_ON_WITH_SETTINGS: Final = 3

# 窗帘电机的 power_state 取值:0=闭合, 1=打开, 2=停止, 3=定位到指定进度。
CURTAIN_CLOSE: Final = 0
CURTAIN_OPEN: Final = 1
CURTAIN_STOP: Final = 2
CURTAIN_POSITION: Final = 3

# V设备(布防型开关)设备上报的 power_state 语义:1=布防(开), 2=撤防(关)。
VSWITCH_STATE_ON: Final = 1
VSWITCH_STATE_OFF: Final = 2

# V设备布防/撤防控制帧载荷(FUNCTION_ARM / FUNCTION_ARM_CONDITION)。
ARM_ON_PAYLOAD: Final = bytes([1, 0, 0, 0])
ARM_OFF_PAYLOAD: Final = bytes([2, 0, 0, 0])

# 联动实体视为「开」的状态集合(开关/阀门/锁)。
LINKED_ON_STATES: Final = ("on", "open", "locked")

FAN_MODE_SPEED_MAP = {
    FAN_LOW: 1,
    FAN_MEDIUM: 2,
    FAN_HIGH: 3,
    FAN_AUTO: 5
}
SPEED_FAN_MODE_MAP = {v: k for k, v in FAN_MODE_SPEED_MAP.items()}

HVAC_MODE_MAP = {
    HVACMode.FAN_ONLY: 0,
    HVACMode.HEAT: 1,
    HVACMode.COOL: 2,
    HVACMode.DRY: 3,
    HVACMode.AUTO: 4,
}

MODE_HVAC_MAP = {v: k for k, v in HVAC_MODE_MAP.items()}
