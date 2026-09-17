import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from . import room_sync
from .const import DOMAIN, SUPPORTED_PLATFORMS, OPTIONS_CONFIG, CONF_DEVICE_ADDR, CONF_GATEWAY_IP
from .leelen.api.HttpApi import HttpApi
from .leelen.utils.LogUtils import LogUtils
from .service import LeelenService

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})
    LogUtils.d(__name__, entry.data)

    hass.data[DOMAIN].setdefault('devices', {})

    device_addr = entry.data[CONF_DEVICE_ADDR]

    all_devices = await HttpApi.get_instance(hass).refresh_devices(device_addr)
    hass.data[DOMAIN]['devices'][entry.entry_id] = all_devices

    gateway_ip = await HttpApi.get_instance(hass).query_gateway_ip()
    # 网关 DHCP 变更 IP 后,云端 dump.db 可能保留旧 LAN IP(连不上真实网关)。
    # 允许用户在 options 里手动覆盖;优先使用覆盖值。
    manual_ip = (entry.options.get(OPTIONS_CONFIG, {}).get(CONF_GATEWAY_IP) or "").strip()
    if manual_ip:
        gateway_ip = manual_ip
    hass.data[DOMAIN][CONF_GATEWAY_IP] = gateway_ip


    service = LeelenService(hass, entry.data)

    hass.data[DOMAIN][entry.entry_id] = {
        "service": service,
    }

    await hass.config_entries.async_forward_entry_setups(entry, SUPPORTED_PLATFORMS)

    # 后台自动同步房间→区域。此处设备注册表条目已由平台实体注册完成,
    # 用 entry 绑定的后台任务避免阻塞 setup(异常已收敛进 SyncStats.note)。
    entry.async_create_background_task(
        hass, room_sync.run_background_sync(hass, entry), name="leelen_home_room_sync"
    )

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
        # stop() 内部会 join 心跳/接收/线程池等后台线程,同步调用会卡死事件循环
        # (与 service.async_restart 一致,放到执行器线程执行)。
        await hass.async_add_executor_job(data["service"].stop)
        hass.data[DOMAIN].pop(entry.entry_id)
    
    # 清理设备数据
    if entry.entry_id in hass.data[DOMAIN].get('devices', {}):
        hass.data[DOMAIN]['devices'].pop(entry.entry_id)

    # 如果没有更多的条目，清理整个DOMAIN数据
    if not hass.data[DOMAIN].get('devices', {}):
        hass.data.pop(DOMAIN)

    return unload_ok
