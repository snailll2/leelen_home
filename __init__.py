import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, SUPPORTED_PLATFORMS, CONF_PHONE, OPTIONS_CONFIG, CONF_DEVICE_ADDR, CONF_GATEWAY_IP
from .leelen.api.HttpApi import HttpApi
from .leelen.utils.LogUtils import LogUtils
from .service import LeelenService

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})
    LogUtils.d(__name__, entry.data)

    hass.data[DOMAIN].setdefault('devices', {})
    # {[entry_id:str]: entities}
    hass.data[DOMAIN].setdefault('entities', {})

    for platform in SUPPORTED_PLATFORMS:
        hass.data[DOMAIN]['entities'][platform] = []

    device_addr = entry.data[CONF_DEVICE_ADDR]

    all_devices = await HttpApi.get_instance(hass).refresh_devices(device_addr)
    hass.data[DOMAIN]['devices'][entry.entry_id] = all_devices

    gateway_ip = await HttpApi.get_instance(hass).query_gateway_ip()
    hass.data[DOMAIN][CONF_GATEWAY_IP] = gateway_ip


    service = LeelenService(hass, entry.data)

    hass.data[DOMAIN][entry.entry_id] = {
        "service": service,
    }

    await hass.config_entries.async_forward_entry_setups(entry, SUPPORTED_PLATFORMS)

    await service.async_start(
        entry.options[OPTIONS_CONFIG] if OPTIONS_CONFIG in entry.options else {}
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # 卸载所有平台
    unload_ok = await hass.config_entries.async_unload_platforms(entry, SUPPORTED_PLATFORMS)
    
    # 停止服务并清理数据
    data = hass.data[DOMAIN].get(entry.entry_id)
    if data is not None:
        data["service"].stop()
        hass.data[DOMAIN].pop(entry.entry_id)
    
    # 清理设备和实体数据
    if entry.entry_id in hass.data[DOMAIN].get('devices', {}):
        hass.data[DOMAIN]['devices'].pop(entry.entry_id)
    
    # 清理entities字典
    if 'entities' in hass.data[DOMAIN]:
        hass.data[DOMAIN]['entities'] = {}
    
    # 如果没有更多的条目，清理整个DOMAIN数据
    if not hass.data[DOMAIN].get('devices', {}):
        hass.data.pop(DOMAIN)

    return unload_ok
