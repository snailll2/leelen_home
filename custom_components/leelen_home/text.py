"""text 平台:只读属性展示(按 PropertyId 命名的 property_* Text 实体)。"""
from __future__ import annotations

import logging
from typing import Optional

from homeassistant.components.text import TextEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .leelen.common import PropertyId
from .platform_helper import async_setup_entry as _setup_platform

_LOGGER = logging.getLogger(__name__)


def _build_entities(device_info, config_entry):
    """按已命名的 property_id 建只读 Text 实体(property_<属性名>)。"""
    entities = []
    # PropertyId.__dict__ 除属性外还含 __module__/__doc__ 等私有成员,统一跳过以下划线开头的键。
    property_ids = {
        attr: value for attr, value in PropertyId.__dict__.items()
        if not attr.startswith("_")
    }
    dev_name = device_info.get("dev_name")
    for property in device_info.get("all_property", []):
        target_id = property.get("property_id")
        for property_name, property_id in property_ids.items():
            if property_id == target_id:
                entities.append(Text(
                    "property_" + property_name,
                    device_info.get("dev_addr"),
                    dev_name,
                    str(property.get("val")),
                    config_entry))
    return entities


async def async_setup_entry(
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up a config entry."""
    await _setup_platform(hass, config_entry, async_add_entities, _build_entities)


class Text(TextEntity):
    """Text entities for Leelen Home."""

    # 只读展示型实体,本集成未实现回写。
    _attr_mode = "text"

    def __init__(self, name, device_id: str, dev_name: str, value: str, config_entry: ConfigEntry):
        """Initialize the Text."""
        self._device_id = device_id
        self._name = name
        self._device_name = dev_name
        self._config_entry = config_entry
        self._value = value

    @property
    def unique_id(self) -> str:
        # 用设备地址 + 属性名拼稳定 key,避免不同设备/属性共用同一唯一 ID 而碰撞。
        return f"leelen_prop_{self._device_id}_{self._name}"

    @property
    def name(self) -> str:
        return self._name

    @property
    def native_max(self):
        return 255

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={("LEELEN_HOME", self._device_id)},
            name=self._device_name,
            manufacturer="LEELEN",
        )

    @property
    def native_value(self) -> Optional[str]:
        """Return the current text value."""
        if isinstance(self._value, str):
            return self._value[:255]
        return self._value
