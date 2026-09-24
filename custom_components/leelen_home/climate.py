"""climate 平台:空调 / 新风 / 地暖三分类。

按 ``logic_srv.logic_type``(**不按 dev_name,不写死任何固定地址**)分派建实体,
控制指令直发每个逻辑服务**自己的** ``logic_addr`` —— 与官方 App 一致,零配置。

- ``AirConditioner``:中心空调/空调执行器/红外/485 等空调类。
- ``FreshAirFan``:新风/通风系统,level 0/1/2/3/0xFE = 关/低/中/高/自动。
- ``FloorHeatingClimate``:地暖,电源位为状态字节 bit4(0x10,官方 App 确认)。
"""
from __future__ import annotations

from typing import Any

from homeassistant.components.climate import (
    ClimateEntity, HVACMode, ClimateEntityFeature,
    DEFAULT_MAX_TEMP, DEFAULT_MIN_TEMP, HVACAction,
    FAN_LOW, FAN_MEDIUM, FAN_HIGH, FAN_AUTO,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    AC_LOGIC_TYPES, FRESH_AIR_LOGIC_TYPES, FLOOR_HEATING_LOGIC_TYPES,
    CLIMATE_LOGIC_TYPES, HVAC_MODE_MAP, MODE_HVAC_MAP,
    FAN_MODE_SPEED_MAP, SPEED_FAN_MODE_MAP, POWER_ON, POWER_ON_WITH_SETTINGS,
)
from .entity_base import LeelenEntity
from .leelen.common.LeelenType import FunctionType, LogicDeviceType
from .leelen.models.ControlModel import ControlModel
from .leelen.states.LinCenterAcState import LinCenterAcState
from .leelen.states.LinSensorState import LinSensorState
from .leelen.utils.LogUtils import LogUtils
from .platform_helper import async_setup_entry as _setup_platform


#: 中心空调/新风/地暖的 logic_type 全集,定义见 const.CLIMATE_LOGIC_TYPES。
SUPPORTED_LOGIC_TYPES = CLIMATE_LOGIC_TYPES

#: 功能码按类型选择(官方 App 全通用功能码,51235 不存在):
#: 空调 146/658/770/242/157/782 → 55297;执行器/DIY 773/778 → 51232。
#: 新风 774/780 → 49185;其余(152/148/771/777/664/783)→ 49156。
#: 地暖 775/779 → 51234;其余(150/662/776)→ 51213。
FUNC_AC_ACTUATOR = {
    LogicDeviceType.TYPE_AC_ACTUATOR,          # 773
    LogicDeviceType.DIY_CENTER_AC,             # 778
}
FUNC_FRESH_ACTUATOR = {
    LogicDeviceType.TYPE_FRESH_ACTUATOR,       # 774
    LogicDeviceType.DIY_REFRESH_AIR,           # 780
}
FUNC_FLOOR_ACTUATOR = {
    LogicDeviceType.TYPE_FLOOR_ACTUATOR,       # 775
    LogicDeviceType.DIY_FLOOR_HEARTING,        # 779
}


def _class_for_logic_type(logic_type):
    if logic_type in AC_LOGIC_TYPES:
        return AirConditioner
    if logic_type in FRESH_AIR_LOGIC_TYPES:
        return FreshAirFan
    if logic_type in FLOOR_HEATING_LOGIC_TYPES:
        return FloorHeatingClimate
    return None


def _build_entities(device_info, config_entry):
    """按 SUPPORTED_LOGIC_TYPES 建实体,按 logic_type 分派到三类。

    尊重网关 ``display`` 列(官方 App 的展示清单):``display==0`` 的逻辑服务
    在官方 App 里被隐藏(面板重复通道),这里同样不建实体。
    """
    entities = []
    for logic_srv in device_info.get("logic_srv", []):
        logic_type = logic_srv.get("logic_type")
        cls = _class_for_logic_type(logic_type)
        if cls is None:
            continue
        if logic_srv.get("display", 1) == 0:
            continue
        entities.append(cls(
            logic_srv.get("logic_addr"),
            logic_srv.get("dev_addr"),
            logic_srv.get("logic_name"),
            device_info.get("dev_name"),
            config_entry,
            logic_type))
    return entities


async def async_setup_entry(
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up a config entry."""
    await _setup_platform(hass, config_entry, async_add_entities, _build_entities)


class AirConditioner(LeelenEntity, ClimateEntity, RestoreEntity):
    """中心空调/空调类实体。"""

    def __init__(self, logic_addr, device_id: str, logic_name: str, dev_name: str,
                 config_entry: ConfigEntry, logic_type: int):
        super().__init__(logic_addr, device_id, logic_name, dev_name, config_entry)
        self._logic_type = logic_type
        self._control_func = (FunctionType.FUNCTION_AC_ACTUATOR if logic_type in FUNC_AC_ACTUATOR
                              else FunctionType.FUNCTION_CENTER_AC)

        self._attr_temperature_unit = UnitOfTemperature.CELSIUS
        self._attr_min_temp = DEFAULT_MIN_TEMP
        self._attr_max_temp = DEFAULT_MAX_TEMP

        self._attr_hvac_action: HVACAction | None = None
        self._attr_hvac_mode: HVACMode = HVACMode.OFF
        self._attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT, HVACMode.COOL,
                                 HVACMode.FAN_ONLY, HVACMode.AUTO]
        self._attr_fan_mode: str = FAN_LOW
        self._attr_fan_modes = [FAN_LOW, FAN_MEDIUM, FAN_HIGH, FAN_AUTO]
        self._attr_target_temperature = 25.0
        self._attr_current_temperature = 25.0
        self._attr_target_temperature_step = 1.0

        self._attr_supported_features = (
            ClimateEntityFeature.TARGET_TEMPERATURE
            | ClimateEntityFeature.FAN_MODE
            | ClimateEntityFeature.TURN_ON
            | ClimateEntityFeature.TURN_OFF
        )

    async def async_added_to_hass(self):
        """恢复上次运行的空调设定(target/hvac_mode/fan_mode)。"""
        await super().async_added_to_hass()
        old_state = await self.async_get_last_state()
        if old_state:
            if "temperature" in old_state.attributes:
                self._attr_target_temperature = float(old_state.attributes["temperature"])
            if "hvac_mode" in old_state.attributes:
                self._attr_hvac_mode = old_state.attributes["hvac_mode"]
            if "fan_mode" in old_state.attributes:
                self._attr_fan_mode = old_state.attributes["fan_mode"]

    @property
    def hvac_mode(self):
        if not self._prop_on:
            return HVACMode.OFF
        return self._attr_hvac_mode

    @property
    def hvac_action(self):
        if not self._prop_on:
            return HVACAction.OFF
        if self.hvac_mode == HVACMode.FAN_ONLY:
            return HVACAction.FAN
        if self.hvac_mode == HVACMode.DRY:
            return HVACAction.DRYING
        if self.hvac_mode == HVACMode.COOL:
            return HVACAction.COOLING
        if self.hvac_mode == HVACMode.HEAT:
            return HVACAction.HEATING
        return HVACAction.IDLE

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode == HVACMode.OFF:
            self._prop_on = False
        else:
            self._prop_on = True
            self._attr_hvac_mode = hvac_mode
        await self._send_control()
        self.async_write_ha_state()

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        self._attr_fan_mode = fan_mode
        if self._prop_on:
            await self._send_control()
        self.async_write_ha_state()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        temperature = kwargs.get("temperature")
        if temperature is None:
            return
        self._attr_target_temperature = temperature
        if self._prop_on:
            await self._send_control()
        self.async_write_ha_state()

    async def _send_control(self):
        """单帧携带开关+模式+风速+目标温度(与官方 App 编码一致)。

        byte0 = (风速<<5) | (温度-16),byte1 = (开关<<3) | 模式。
        """
        power = 1 if self._prop_on else 0
        mode = HVAC_MODE_MAP.get(self._attr_hvac_mode, 2)
        speed = FAN_MODE_SPEED_MAP.get(self._attr_fan_mode, 3)
        temp_encoded = max(0, min(15, int(self._attr_target_temperature) - 16))
        control_bytes = bytes([(speed << 5) | temp_encoded, (power << 3) | mode])
        ControlModel.get_instance().device_control(
            self._logic_addr, self._control_func, control_bytes)

    async def update_state(self, state: LinCenterAcState | LinSensorState):
        LogUtils.d(f"🧯 {self._name} ac update {state}")
        if isinstance(state, LinSensorState):
            if state.get_service_type() == FunctionType.FUNCTION_AC_TEMP:
                self._attr_current_temperature = state.get_value()
            return

        # 空调字段全部无条件回写:mode/speed/temp 是设备上报的确定性字段,
        # 0 本身就是合法值(如 FAN_ONLY=0、temp 0 表示沿用),不能用 if 守卫吞掉。
        self._prop_on = state.power_state in (POWER_ON, POWER_ON_WITH_SETTINGS)
        self._attr_hvac_mode = MODE_HVAC_MAP.get(state.mode, HVACMode.FAN_ONLY)
        self._attr_fan_mode = SPEED_FAN_MODE_MAP.get(state.speed, FAN_LOW)
        self._attr_target_temperature = state.setting_temperature


class FreshAirFan(LeelenEntity, ClimateEntity, RestoreEntity):
    """新风/通风系统实体,level 0/1/2/3/0xFE = 关/低/中/高/自动。"""

    def __init__(self, logic_addr, device_id: str, logic_name: str, dev_name: str,
                 config_entry: ConfigEntry, logic_type: int):
        super().__init__(logic_addr, device_id, logic_name, dev_name, config_entry)
        self._logic_type = logic_type
        self._control_func = (FunctionType.FUNCTION_FRESH_ACTUATOR if logic_type in FUNC_FRESH_ACTUATOR
                              else FunctionType.FUNCTION_LEVEL_GEARS)

        self._prop_on = False
        self._speed_level = 0
        self._attr_hvac_mode: HVACMode = HVACMode.FAN_ONLY
        self._attr_hvac_modes = [HVACMode.OFF, HVACMode.FAN_ONLY]
        self._attr_fan_mode: str = FAN_LOW
        self._attr_fan_modes = [FAN_LOW, FAN_MEDIUM, FAN_HIGH, FAN_AUTO]
        self._attr_temperature_unit = UnitOfTemperature.CELSIUS
        self._attr_target_temperature = None
        self._attr_current_temperature = None
        self._attr_supported_features = (
            ClimateEntityFeature.FAN_MODE
            | ClimateEntityFeature.TURN_ON
            | ClimateEntityFeature.TURN_OFF
        )

    async def async_added_to_hass(self):
        """恢复上次运行的新风风速。"""
        await super().async_added_to_hass()
        old_state = await self.async_get_last_state()
        if old_state:
            if "fan_mode" in old_state.attributes:
                self._attr_fan_mode = old_state.attributes["fan_mode"]
                speed_map = {FAN_LOW: 1, FAN_MEDIUM: 2, FAN_HIGH: 3, FAN_AUTO: 0xFE}
                self._speed_level = speed_map.get(old_state.attributes["fan_mode"], 2)
            if "hvac_mode" in old_state.attributes:
                self._attr_hvac_mode = old_state.attributes["hvac_mode"]

    @property
    def hvac_mode(self):
        return HVACMode.FAN_ONLY if self._prop_on else HVACMode.OFF

    @property
    def hvac_action(self):
        return HVACAction.FAN if self._prop_on else HVACAction.OFF

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode == HVACMode.OFF:
            await self.async_turn_off()
        else:
            await self.async_turn_on()

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        speed_map = {FAN_LOW: 1, FAN_MEDIUM: 2, FAN_HIGH: 3, FAN_AUTO: 0xFE}
        self._speed_level = speed_map.get(fan_mode, 2)
        self._attr_fan_mode = fan_mode
        if self._prop_on:
            await self._send_control()
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        self._prop_on = True
        if self._speed_level == 0:
            self._speed_level = 2
            self._attr_fan_mode = FAN_MEDIUM
        await self._send_control()
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._prop_on = False
        await self._send_control()
        self.async_write_ha_state()

    async def _send_control(self):
        """level 映射 0/1/2/3/0xFE → 关/低/中/高/自动,单字节载荷直发自身地址。"""
        if not self._prop_on:
            level = 0x00
        else:
            level = {1: 0x01, 2: 0x02, 3: 0x03, 0xFE: 0xFE}.get(self._speed_level, 0x02)
        ControlModel.get_instance().device_control(
            self._logic_addr, self._control_func, bytes([level]))

    async def update_state(self, state: LinCenterAcState | LinSensorState):
        LogUtils.d(f"🧯 {self._name} fresh update {state}")
        service_type = state.get_service_type()
        if service_type not in (FunctionType.FUNCTION_FRESH_ACTUATOR,
                                FunctionType.FUNCTION_LEVEL_GEARS):
            return
        # 第一个字节即 level(0/1/2/3/0xFE);CommonModel 已把该字节放入 power_state 与 state。
        raw = getattr(state, "state", None)
        val = raw[0] if isinstance(raw, bytes) and raw else state.power_state
        self._prop_on = val != 0
        if val == 0:
            self._speed_level = 0
            self._attr_fan_mode = FAN_LOW
        elif val == 1:
            self._speed_level = 1
            self._attr_fan_mode = FAN_LOW
        elif val == 2:
            self._speed_level = 2
            self._attr_fan_mode = FAN_MEDIUM
        elif val == 3:
            self._speed_level = 3
            self._attr_fan_mode = FAN_HIGH
        elif val == 0xFE:
            self._speed_level = 0xFE
            self._attr_fan_mode = FAN_AUTO


class FloorHeatingClimate(LeelenEntity, ClimateEntity, RestoreEntity):
    """地暖实体;电源位 = 状态字节 bit4(官方 App 确认),设定温度 = 首字节。"""

    def __init__(self, logic_addr, device_id: str, logic_name: str, dev_name: str,
                 config_entry: ConfigEntry, logic_type: int):
        super().__init__(logic_addr, device_id, logic_name, dev_name, config_entry)
        self._logic_type = logic_type
        self._control_func = (FunctionType.FUNCTION_FLOOR_ACTUATOR if logic_type in FUNC_FLOOR_ACTUATOR
                              else FunctionType.FUNCTION_FLOOR_HEATING)

        self._attr_temperature_unit = UnitOfTemperature.CELSIUS
        self._attr_min_temp = DEFAULT_MIN_TEMP
        self._attr_max_temp = DEFAULT_MAX_TEMP

        self._attr_target_temperature = 22.0
        self._attr_current_temperature = 22.0
        self._attr_target_temperature_step = 1.0
        self._attr_hvac_mode: HVACMode = HVACMode.OFF
        self._attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT]
        self._attr_supported_features = (
            ClimateEntityFeature.TARGET_TEMPERATURE
            | ClimateEntityFeature.TURN_ON
            | ClimateEntityFeature.TURN_OFF
        )
        #: 上报状态里的「其余字节」缓存,开关只改 bit4、调温不动开关位,避免误关。
        self._last_state_byte = 0xcc

    async def async_added_to_hass(self):
        """恢复上次运行的地暖设定(target/hvac_mode)。"""
        await super().async_added_to_hass()
        old_state = await self.async_get_last_state()
        if old_state:
            if "temperature" in old_state.attributes:
                self._attr_target_temperature = float(old_state.attributes["temperature"])
            if "hvac_mode" in old_state.attributes:
                self._attr_hvac_mode = old_state.attributes["hvac_mode"]

    @property
    def hvac_mode(self):
        return HVACMode.HEAT if self._prop_on else HVACMode.OFF

    @property
    def hvac_action(self):
        return HVACAction.HEATING if self._prop_on else HVACAction.OFF

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        self._prop_on = hvac_mode != HVACMode.OFF
        await self._send_control()
        self.async_write_ha_state()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        # 只改温度,不重发开关指令 —— 避免调温帧盖掉当前的开关位导致误关。
        temperature = kwargs.get("temperature")
        if temperature is None:
            return
        self._attr_target_temperature = temperature
        await self._send_temperature()
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        self._prop_on = True
        await self._send_control()
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._prop_on = False
        await self._send_control()
        self.async_write_ha_state()

    async def _send_control(self):
        """开关指令:状态字节置/清 bit4,与设定温度一起发到自身地址。"""
        temp = int(self._attr_target_temperature)
        if self._prop_on:
            new_state_byte = self._last_state_byte | 0x10
        else:
            new_state_byte = self._last_state_byte & ~0x10
        ControlModel.get_instance().device_control(
            self._logic_addr, self._control_func, bytes([temp, new_state_byte]))

    async def _send_temperature(self):
        temp = int(self._attr_target_temperature)
        ControlModel.get_instance().device_control(
            self._logic_addr, self._control_func, bytes([temp, self._last_state_byte]))

    async def update_state(self, state: LinCenterAcState | LinSensorState):
        LogUtils.d(f"🧯 {self._name} floor update {state}")
        service_type = state.get_service_type()
        if service_type in (FunctionType.FUNCTION_FLOOR_ACTUATOR,   # 51234
                            FunctionType.FUNCTION_FLOOR_HEATING,    # 51213
                            51235):                                 # 兼容既旧变体
            raw = getattr(state, "state", None)
            if raw and len(raw) >= 2:
                try:
                    self._attr_target_temperature = float(raw[0])
                except (ValueError, TypeError):
                    pass
                self._prop_on = (raw[1] & 0x10) == 0x10
                self._attr_hvac_mode = HVACMode.HEAT if self._prop_on else HVACMode.OFF
                self._last_state_byte = raw[1]
        elif service_type == FunctionType.FUNCTION_TEMPERATURE:  # 18442 室温
            if state.get_service_address() == self._logic_addr:
                val = state.get_value()
                if isinstance(val, bytes) and len(val) >= 2:
                    val = int.from_bytes(val[:2], byteorder='big') / 10.0
                try:
                    self._attr_current_temperature = float(val) if val is not None \
                        else self._attr_current_temperature
                except (ValueError, TypeError):
                    pass