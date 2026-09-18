"""cover 平台:无线窗帘(TYPE_WIRELESS_CURTAIN)。"""
from __future__ import annotations

from typing import Any

from homeassistant.components.cover import CoverEntity, CoverDeviceClass, CoverEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (CURTAIN_CLOSE, CURTAIN_OPEN, CURTAIN_POSITION, CURTAIN_STOP,
                    COVER_LOGIC_TYPES)
from .entity_base import LeelenEntity
from .leelen.common.LeelenType import LogicDeviceType
from .leelen.states.LinBaseState import LinBaseState
from .leelen.models.ControlModel import ControlModel
from .leelen.states.LinCurtainMotorState import LinCurtainMotorState
from .leelen.utils.LogUtils import LogUtils
from .platform_helper import async_setup_entry as _setup_platform



def _build_entities(device_info, config_entry):
    """按 logic_type 建实体:TYPE_WIRELESS_CURTAIN→Cover。"""
    entities = []
    for logic_srv in device_info.get("logic_srv", []):
        if logic_srv.get("logic_type") in COVER_LOGIC_TYPES:
            entities.append(Cover(
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


class Cover(LeelenEntity, CoverEntity):
    """cover 平台的无线窗帘实体。"""

    def __init__(self, logic_addr, device_id: str, name: str, dev_name: str, config_entry: ConfigEntry):
        super().__init__(logic_addr, device_id, name, dev_name, config_entry)
        self._attr_current_cover_position = 0

        self._lin = LinCurtainMotorState()
        self._lin.service_address = logic_addr
        self._lin.service_type = LogicDeviceType.TYPE_WIRELESS_CURTAIN
        self._lin.set_power_state(CURTAIN_OPEN)
        self._lin.set_progress(0)
        self._attr_supported_features = (
            CoverEntityFeature.OPEN
            | CoverEntityFeature.CLOSE
            | CoverEntityFeature.STOP
            | CoverEntityFeature.SET_POSITION
        )
        self._attr_is_closed = self._lin.progress == 0

    @property
    def device_class(self):
        return CoverDeviceClass.CURTAIN

    @property
    def is_closed(self):
        return self._attr_is_closed

    @property
    def current_cover_position(self):
        return self._attr_current_cover_position

    async def async_open_cover(self, **kwargs: Any) -> None:
        LogUtils.d("async_open_cover")
        self._lin.set_power_state(CURTAIN_OPEN)
        ControlModel.get_instance().control(self._lin)
        self._attr_is_closed = False
        self.async_write_ha_state()

    async def async_close_cover(self, **kwargs: Any) -> None:
        LogUtils.d("async_close_cover")
        self._lin.set_power_state(CURTAIN_CLOSE)
        ControlModel.get_instance().control(self._lin)
        self._attr_is_closed = True
        self.async_write_ha_state()

    async def async_stop_cover(self, **kwargs: Any) -> None:
        LogUtils.d("async_stop_cover")
        self._lin.set_power_state(CURTAIN_STOP)
        ControlModel.get_instance().control(self._lin)
        self.async_write_ha_state()

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        position = kwargs.get("position", 0)
        self._lin.set_power_state(CURTAIN_POSITION)
        self._lin.set_progress(position)
        LogUtils.d("async_set_cover_position", kwargs)
        ControlModel.get_instance().control(self._lin)
        self._attr_current_cover_position = position
        self.async_write_ha_state()

    async def update_state(self, state: LinCurtainMotorState | LinBaseState):
        LogUtils.d(f"🧯 {self._name} update {state}")
        self._lin.set_power_state(state.power_state)
        if isinstance(state, LinCurtainMotorState):
            # 拷贝进度到局部,避免改写传入的 state 对象(脚下留神外部状态)
            progress = state.progress
            if progress <= 5:
                progress = 0
            self._attr_is_closed = progress == 0
            self._attr_current_cover_position = progress
            self._lin.set_progress(progress)
