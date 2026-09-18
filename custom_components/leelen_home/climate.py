"""climate 平台:中心空调/地暖/新风(SUPPORTED_LOGIC_TYPES)。"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import ClimateEntity, HVACMode, ClimateEntityFeature, \
    DEFAULT_MAX_HUMIDITY, DEFAULT_MAX_TEMP, DEFAULT_MIN_HUMIDITY, DEFAULT_MIN_TEMP, HVACAction, \
    FAN_LOW, FAN_MEDIUM, FAN_HIGH, FAN_ON, FAN_OFF
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (HVAC_MODE_MAP, FAN_MODE_SPEED_MAP, SPEED_FAN_MODE_MAP, MODE_HVAC_MAP,
                    POWER_OFF, POWER_ON, POWER_ON_WITH_SETTINGS, CLIMATE_LOGIC_TYPES)
from .entity_base import LeelenEntity
from .leelen.common.LeelenType import FunctionType, LogicDeviceType
from .leelen.models.ControlModel import ControlModel
from .leelen.states.LinCenterAcState import LinCenterAcState
from .leelen.states.LinSensorState import LinSensorState
from .leelen.utils.LogUtils import LogUtils
from .platform_helper import async_setup_entry as _setup_platform

_LOGGER = logging.getLogger(__name__)

#: 中心空调/地暖/新风的 logic_type,定义见 const.CLIMATE_LOGIC_TYPES。
SUPPORTED_LOGIC_TYPES = CLIMATE_LOGIC_TYPES


def _build_entities(device_info, config_entry):
    """按 SUPPORTED_LOGIC_TYPES 建实体:中心空调/地暖/新风统一为 Climate。"""
    entities = []
    for logic_srv in device_info.get("logic_srv", []):
        if logic_srv.get("logic_type") in SUPPORTED_LOGIC_TYPES:
            entities.append(Climate(
                logic_srv.get("logic_addr"),
                logic_srv.get("dev_addr"),
                logic_srv.get("logic_name"),
                device_info.get("dev_name"),
                config_entry))
    return entities


async def async_setup_entry(
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up a config entry."""
    await _setup_platform(hass, config_entry, async_add_entities, _build_entities)


class Climate(LeelenEntity, ClimateEntity, RestoreEntity):
    """Climate entities for Leelen Home."""

    def __init__(self, logic_addr, device_id: str, logic_name: str, dev_name: str, config_entry: ConfigEntry):
        super().__init__(logic_addr, device_id, logic_name, dev_name, config_entry)

        self._attr_device_class = 'climate'

        self._attr_target_temperature = 25.0
        self._attr_current_temperature = 25.0
        self._attr_temperature_unit: str = ""
        self._attr_min_temp: float = DEFAULT_MIN_TEMP
        self._attr_max_temp: float = DEFAULT_MAX_TEMP

        self._attr_is_aux_heat: bool = False

        self._attr_hvac_action: HVACAction = None
        self._attr_hvac_mode: HVACMode = None
        self._attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT, HVACMode.COOL, HVACMode.FAN_ONLY, HVACMode.AUTO]

        self._attr_fan_mode: str = FAN_LOW
        self._attr_fan_modes: list[str] = [FAN_LOW, FAN_MEDIUM, FAN_HIGH, FAN_ON, FAN_OFF]

        self._attr_target_humidity: int = 0
        self._attr_max_humidity: int = DEFAULT_MAX_HUMIDITY
        self._attr_min_humidity: int = DEFAULT_MIN_HUMIDITY

        self._attr_precision: float = 0.1
        self._attr_preset_mode: str | None = None
        self._attr_preset_modes: list[str] = []

        self._attr_swing_mode: str = ""
        self._attr_swing_modes: list[str] = []

        self._attr_supported_features: ClimateEntityFeature = ClimateEntityFeature(0)
        self._attr_supported_features |= ClimateEntityFeature.FAN_MODE
        # self._attr_supported_features |= ClimateEntityFeature.SWING_MODE
        self._attr_supported_features |= ClimateEntityFeature.TARGET_TEMPERATURE
        # self._attr_supported_features |= ClimateEntityFeature.PRESET_MODE
        self._attr_supported_features |= ClimateEntityFeature.TURN_ON
        self._attr_supported_features |= ClimateEntityFeature.TURN_OFF

        self._lin = LinCenterAcState()
        self._lin.service_address = logic_addr
        self._lin.service_type = LogicDeviceType.TYPE_CENTER_AIR_CONDITIONER
        self._lin.set_mode(2)
        self._lin.set_speed(1)
        self._lin.set_setting_temperature(self._attr_target_temperature)
        self._lin.set_power_state(POWER_ON_WITH_SETTINGS)

    async def async_added_to_hass(self):
        """在 HA 加载这个实体时调用，尝试恢复状态"""
        await super().async_added_to_hass()
        old_state = await self.async_get_last_state()

        if old_state:

            if "temperature" in old_state.attributes:
                self._attr_target_temperature = float(old_state.attributes["temperature"])
                self._lin.set_setting_temperature(self._attr_target_temperature)

            if "hvac_mode" in old_state.attributes:
                self._attr_hvac_mode = old_state.attributes["hvac_mode"]

                mode = HVAC_MODE_MAP.get(self._attr_hvac_mode)
                if mode is not None:
                    self._lin.set_mode(mode)

            if "fan_mode" in old_state.attributes:
                fan_mode = old_state.attributes["fan_mode"]
                self._attr_fan_mode = fan_mode

                speed = FAN_MODE_SPEED_MAP.get(fan_mode.lower(), 0)
                self._lin.set_speed(speed)

    @property
    def temperature_unit(self):
        prop = self._attr_temperature_unit
        if prop:
            if prop in ['celsius', UnitOfTemperature.CELSIUS, '℃']:
                return UnitOfTemperature.CELSIUS
            if prop in ['fahrenheit', UnitOfTemperature.FAHRENHEIT]:
                return UnitOfTemperature.FAHRENHEIT
            if prop in ['kelvin', UnitOfTemperature.KELVIN]:
                return UnitOfTemperature.KELVIN
        return UnitOfTemperature.CELSIUS

    @property
    def hvac_mode(self):
        if not self._prop_on:
            return HVACMode.OFF
        return self._attr_hvac_mode

    @property
    def hvac_modes(self):
        return self._attr_hvac_modes

    @property
    def hvac_action(self):
        """Return the current running hvac operation if supported.

        Need to be one of HVACAction.*.
        """
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

    @property
    def preset_mode(self):
        # 本集成未实现预设模式(preset);preset_mode/preset_modes 应返回 preset 语义,
        # 而不是 HVAC 模式。无预设时返回 None。
        return None

    @property
    def preset_modes(self):
        return []

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        if hvac_mode == HVACMode.OFF:
            await self.async_turn_off()
            self._attr_hvac_mode = HVACMode.OFF
            self.async_write_ha_state()
            return

        # 单帧同时携带「开机 + 模式 + 目标温度」:不再先 async_turn_on 多发一帧电源
        # (旧实现一次模式切换会连发两帧,失败时设备可能停在中间态)。
        self._prop_on = True
        self._lin.set_power_state(POWER_ON_WITH_SETTINGS)
        mode = HVAC_MODE_MAP.get(hvac_mode)
        if mode is not None:
            self._lin.set_mode(mode)
        self._attr_hvac_mode = hvac_mode
        ControlModel.get_instance().control(self._lin, 0)
        self.async_write_ha_state()

    @property
    def fan_mode(self):
        return self._attr_fan_mode

    @property
    def fan_modes(self):
        return self._attr_fan_modes

    @property
    def min_temp(self):
        return max(self._attr_min_temp, DEFAULT_MIN_TEMP)

    @property
    def max_temp(self):
        return min(self._attr_max_temp, DEFAULT_MAX_TEMP)

    @property
    def target_temperature(self):
        return self._attr_target_temperature

    @property
    def current_temperature(self):
        return self._attr_current_temperature

    @property
    def target_temperature_step(self):
        return 1

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        self._lin.set_power_state(POWER_ON_WITH_SETTINGS)
        speed = FAN_MODE_SPEED_MAP.get(fan_mode.lower(), 0)
        self._lin.set_speed(speed)
        self._attr_fan_mode = fan_mode
        ControlModel.get_instance().control(self._lin, 0)
        self.async_write_ha_state()

    @property
    def current_humidity(self):
        return None

    @property
    def target_humidity(self):
        return None

    @property
    def min_humidity(self):
        return DEFAULT_MIN_HUMIDITY

    @property
    def max_humidity(self):
        return DEFAULT_MAX_HUMIDITY

    def set_humidity(self, humidity):
        return False

    async def async_set_humidity(self, humidity: int) -> None:
        pass

    async def async_set_swing_mode(self, swing_mode: str) -> None:
        pass

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        pass

    async def async_set_temperature(self, **kwargs):
        temperature = kwargs.get("temperature")
        if temperature is None:
            return
        self._attr_target_temperature = temperature
        self._lin.set_power_state(POWER_ON_WITH_SETTINGS)
        self._lin.set_setting_temperature(temperature)
        ControlModel.get_instance().control(self._lin)
        self.async_write_ha_state()

    def turn_on(self, **kwargs):
        # 先组装好 power/温度再 control:control 在调用时即取值打包,顺序颠倒会丢字段
        self._lin.set_power_state(POWER_ON)
        self._lin.set_setting_temperature(self._attr_target_temperature)
        ControlModel.get_instance().control(self._lin)
        self._prop_on = True
        return True

    def turn_off(self, **kwargs):
        self._lin.set_power_state(POWER_OFF)
        ControlModel.get_instance().control(self._lin)
        self._prop_on = False
        return True

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.hass.async_add_executor_job(self.turn_on)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.hass.async_add_executor_job(self.turn_off)
        self.async_write_ha_state()

    async def update_state(self, state: LinCenterAcState | LinSensorState):
        LogUtils.d(f"🧯 {self._name} climate update {state}")

        if isinstance(state, LinSensorState):
            if state.get_service_type() == FunctionType.FUNCTION_AC_TEMP:
                self._attr_current_temperature = state.get_value()
            return

        # 电源状态是状态报告的基础,按原语义无条件更新(power_state == 1 表示开)
        self._prop_on = state.power_state == POWER_ON
        # mode/speed/setting_temperature 的默认值是 0,若上报帧未携带则该字段为 0,
        # 不应回写覆盖已确认的模式/风速/目标温度(否则连续上报会互相覆盖成不完整状态)
        if state.mode:
            self._attr_hvac_mode = MODE_HVAC_MAP.get(state.mode, HVACMode.FAN_ONLY)
        if state.speed:
            self._attr_fan_mode = SPEED_FAN_MODE_MAP.get(state.speed, FAN_LOW)
        if state.setting_temperature:
            self._attr_target_temperature = state.setting_temperature
