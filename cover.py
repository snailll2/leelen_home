# # -*- coding: utf-8 -*-
# """
#
# Light entities for Xiaomi Home.
# """
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.cover import CoverEntity, CoverDeviceClass, CoverEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import LogUtils
from .const import DOMAIN
from .leelen.common.LeelenType import *
from .leelen.models.ControlModel import ControlModel
from .leelen.states.LinCurtainMotorState import LinCurtainMotorState

_LOGGER = logging.getLogger(__name__)


async def setup_devices_from_db(hass, config_entry, async_add_entities):
    device_list: list = hass.data[DOMAIN]['devices'].get(config_entry.entry_id) or []
    # 注册设备
    entities = []
    device_registry = dr.async_get(hass)
    for device_info in device_list:
        for logic_srv in device_info.get("logic_srv", []):
            if logic_srv.get("logic_type") in [LogicDeviceType.TYPE_WIRELESS_CURTAIN]:
                entity = Cover(logic_srv.get("logic_addr"),
                               logic_srv.get("dev_addr"),
                               logic_srv.get("logic_name"),
                               device_info.get("dev_name"),
                               config_entry)
                hass.data[DOMAIN]["entities"][entity.unique_id] = entity
                entities.append(entity)
        # 为每个设备创建 Light 实体
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


class Cover(CoverEntity):
    """Light entities for Leelen Home."""

    def __init__(self, logic_addr, device_id: str, name: str,dev_name:str, config_entry: ConfigEntry):
        """Initialize the Light."""

        self._device_id = device_id
        self._name = name
        self._device_name = dev_name
        self._logic_addr = logic_addr
        self._config_entry = config_entry
        self.__attr_current_cover_position = 0

        self._lin = LinCurtainMotorState()
        self._lin.service_address = logic_addr
        self._lin.service_type = LogicDeviceType.TYPE_WIRELESS_CURTAIN
        self._lin.set_power_state(1)
        self._lin.set_progress(0)
        self._attr_supported_features = CoverEntityFeature.OPEN | CoverEntityFeature.CLOSE | CoverEntityFeature.STOP | CoverEntityFeature.SET_POSITION
        self._attr_is_closed = self._lin.progress == 0

    @property
    def unique_id(self) -> str:
        return f"leelen_logic_addr_{self._logic_addr}"

    @property
    def name(self) -> str:
        return self._name

    @property
    def device_class(self):
        return CoverDeviceClass.CURTAIN

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={("LEELEN_HOME", self._device_id)},
            name=self._device_name,
            manufacturer="LEELEN",
        )

    @property
    def is_closed(self):
        return self._lin.progress == 0

    @property
    def current_cover_position(self):
        return self._lin.progress

    async def async_open_cover(self, **kwargs: Any) -> None:
        _LOGGER.info("async_open_cover")
        self._lin.set_power_state(1)
        ControlModel.get_instance().control(self._lin)
        self._attr_is_closed = False
        self.async_write_ha_state()

    async def async_close_cover(self, **kwargs: Any) -> None:
        _LOGGER.info("async_close_cover")
        self._lin.set_power_state(0)
        ControlModel.get_instance().control(self._lin)
        self._attr_is_closed = True
        self.async_write_ha_state()

    async def async_stop_cover(self, **kwargs: Any) -> None:
        _LOGGER.info("async_stop_cover")
        self._lin.set_power_state(2)
        ControlModel.get_instance().control(self._lin)
        self.async_write_ha_state()

    async def async_set_cover_position(self, **kwargs: Any) -> None:
        position = kwargs.get("position", 0)
        self._lin.set_power_state(3)
        self._lin.set_progress(position)
        LogUtils.d("async_set_cover_position", kwargs)
        ControlModel.get_instance().control(self._lin)
        self._attr_current_cover_position = position
        self.async_write_ha_state()

    async def update_state(self, state: LinCurtainMotorState | LinBaseState):
        LogUtils.d(f"🧯 {self._name} update {state}")
        self._lin.set_power_state(state.power_state)
        if isinstance(state,LinCurtainMotorState):
            self._attr_is_closed = state.progress == 0
            if state.progress <=5 :
                state.progress = 0
                
            self._lin.set_progress(state.progress)
            self._attr_current_cover_position = state.progress
