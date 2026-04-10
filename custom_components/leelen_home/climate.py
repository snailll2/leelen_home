# # -*- coding: utf-8 -*-
# """
#
# Light entities for Xiaomi Home.
# """
"""Climate entities for Leelen Home."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    HVACMode,
    ClimateEntityFeature,
    DEFAULT_MAX_HUMIDITY,
    DEFAULT_MAX_TEMP,
    DEFAULT_MIN_HUMIDITY,
    DEFAULT_MIN_TEMP,
    HVACAction,
    FAN_LOW,
    FAN_MEDIUM,
    FAN_HIGH,
    FAN_ON,
    FAN_OFF,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN, HVAC_MODE_MAP, FAN_MODE_SPEED_MAP, SPEED_FAN_MODE_MAP, MODE_HVAC_MAP
from .leelen.common.LeelenType import LogicDeviceType, FunctionType
from .leelen.models.ControlModel import ControlModel
from .leelen.states.LinCenterAcState import LinCenterAcState
from .leelen.states.LinSensorState import LinSensorState
from .leelen.utils.LogUtils import LogUtils


_LOGGER = logging.getLogger(__name__)


async def setup_devices_from_db(hass, config_entry, async_add_entities):
    device_list: list = hass.data[DOMAIN]['devices'].get(config_entry.entry_id) or []
    # 注册设备
    entities = []
    for device_info in device_list:
        for logic_srv in device_info.get("logic_srv", []):
            if logic_srv.get("logic_type") in [LogicDeviceType.TYPE_CENTER_AIR_CONDITIONER]:
                entity = Climate(logic_srv.get("logic_addr"),
                                 logic_srv.get("dev_addr"),
                                 logic_srv.get("logic_name"),
                                 device_info.get("dev_name"),
                                 config_entry)
                hass.data[DOMAIN]["entities"][entity.unique_id] = entity
                entities.append(entity)
    # 添加实体到 HA
    async_add_entities(entities)


async def async_setup_entry(
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up a config entry."""

    await setup_devices_from_db(hass, config_entry, async_add_entities)

    async def handle_refresh():
        await setup_devices_from_db(hass, config_entry, async_add_entities)

    async_dispatcher_connect(hass, "leelen_integration_device_refresh", handle_refresh)


class Climate(ClimateEntity, RestoreEntity):
    """Climate entity for Leelen Home."""

    def __init__(
        self,
        logic_addr: int,
        device_id: str,
        logic_name: str,
        dev_name: str,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the climate entity."""
        self._device_id = device_id
        self._name = logic_name
        self._device_name = dev_name
        self._logic_addr = logic_addr
        self._config_entry = config_entry
        self._prop_on = False
        self._attr_device_class = 'climate'
        # Temperature settings
        self._attr_target_temperature = 25.0
        self._attr_current_temperature = 25.0
        self._attr_temperature_unit = UnitOfTemperature.CELSIUS
        self._attr_min_temp = DEFAULT_MIN_TEMP
        self._attr_max_temp = DEFAULT_MAX_TEMP

        # HVAC settings
        self._attr_hvac_mode = HVACMode.OFF
        self._attr_hvac_modes = [
            HVACMode.OFF,
            HVACMode.HEAT,
            HVACMode.COOL,
            HVACMode.FAN_ONLY,
            HVACMode.AUTO,
        ]
        self._attr_hvac_action = HVACAction.OFF

        # Fan settings
        self._attr_fan_mode = FAN_LOW
        self._attr_fan_modes = [FAN_LOW, FAN_MEDIUM, FAN_HIGH, FAN_ON, FAN_OFF]

        # Humidity settings
        self._attr_target_humidity = 0
        self._attr_current_humidity = None
        self._attr_max_humidity = DEFAULT_MAX_HUMIDITY
        self._attr_min_humidity = DEFAULT_MIN_HUMIDITY

        # Supported features
        self._attr_supported_features = (
            ClimateEntityFeature.FAN_MODE
            | ClimateEntityFeature.TARGET_TEMPERATURE
            | ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
            | ClimateEntityFeature.TURN_ON
            | ClimateEntityFeature.TURN_OFF
        )

        # Initialize state object
        self._lin = LinCenterAcState()
        self._lin.service_address = logic_addr
        self._lin.service_type = LogicDeviceType.TYPE_CENTER_AIR_CONDITIONER
        self._lin.set_mode(2)
        self._lin.set_speed(1)
        self._lin.set_setting_temperature(self._attr_target_temperature)
        self._lin.set_power_state(3)
    
    
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
    def unique_id(self) -> str:
        return f"leelen_logic_addr_{self._logic_addr}"

    @property
    def name(self) -> str:
        return self._name

    @property
    def temperature_unit(self) -> str:
        """Return the unit of measurement."""
        return self._attr_temperature_unit

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={("LEELEN_HOME", self._device_id)},
            name=self._device_name,
            manufacturer="LEELEN",
        )

    @property
    def hvac_mode(self) -> HVACMode:
        """Return current HVAC mode."""
        if not self._prop_on:
            return HVACMode.OFF
        return self._attr_hvac_mode
    @property
    def hvac_modes(self):
        return self._attr_hvac_modes
    @property
    def hvac_action(self) -> HVACAction:
        """Return current HVAC action."""
        if not self._prop_on:
            return HVACAction.OFF
        if self._attr_hvac_mode == HVACMode.FAN_ONLY:
            return HVACAction.FAN
        if self._attr_hvac_mode == HVACMode.DRY:
            return HVACAction.DRYING
        if self._attr_hvac_mode == HVACMode.COOL:
            return HVACAction.COOLING
        if self._attr_hvac_mode == HVACMode.HEAT:
            return HVACAction.HEATING
        return HVACAction.IDLE
    @property
    def preset_mode(self):
        if not self.is_on:
            return HVACMode.OFF
        return HVACMode.HEAT_COOL

    @property
    def preset_modes(self):
        return self.hvac_modes
    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set HVAC mode."""
        if hvac_mode == HVACMode.OFF:
            await self.async_turn_off()
            return

        await self.async_turn_on()
        self._lin.set_power_state(3)

        mode = HVAC_MODE_MAP.get(hvac_mode)
        if mode is not None:
            self._lin.set_mode(mode)

        ControlModel.get_instance().control(self._lin, 0)
        self._attr_hvac_mode = hvac_mode
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

    @property
    def target_temperature_high(self):
        return self.max_temp

    @property
    def target_temperature_low(self):
        return self.min_temp
    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set fan mode."""
        self._lin.set_power_state(3)
        speed = FAN_MODE_SPEED_MAP.get(fan_mode.lower(), 0)
        self._lin.set_speed(speed)
        self._attr_fan_mode = fan_mode
        ControlModel.get_instance().control(self._lin, 0)
        self.async_write_ha_state()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set target temperature."""
        temperature = kwargs.get("temperature")
        if temperature is None:
            return
        self._attr_target_temperature = temperature
        self._lin.power_state = 3
        self._lin.setting_temperature = temperature
        ControlModel.get_instance().control(self._lin)
        self.async_write_ha_state()

    def turn_on(self, **kwargs: Any) -> None:
        """Turn on the climate device."""
        self._lin.power_state = 1
        ControlModel.get_instance().control(self._lin)
        self._lin.set_setting_temperature(self._attr_target_temperature)
        self._prop_on = True

    def turn_off(self, **kwargs: Any) -> None:
        """Turn off the climate device."""
        self._lin.power_state = 0
        ControlModel.get_instance().control(self._lin)
        self._prop_on = False

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Async turn on."""
        await self.hass.async_add_executor_job(self.turn_on)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Async turn off."""
        await self.hass.async_add_executor_job(self.turn_off)
        self.async_write_ha_state()

    async def update_state(self, state: LinCenterAcState | LinSensorState) -> None:
        """Update state from device."""
        LogUtils.d(__name__, f"Climate {self._name} update: {state}")

        if state.get_service_type() == FunctionType.FUNCTION_AC_TEMP:
            self._attr_current_temperature = state.get_value()
        else:
            self._prop_on = state.power_state == 1
            self._attr_fan_mode = SPEED_FAN_MODE_MAP.get(state.speed, FAN_LOW)
            self._attr_hvac_mode = MODE_HVAC_MAP.get(state.mode, HVACMode.FAN_ONLY)
            self._attr_target_temperature = state.setting_temperature
