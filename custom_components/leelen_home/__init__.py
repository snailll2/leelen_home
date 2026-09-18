import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from . import room_sync
from .const import DOMAIN, SUPPORTED_PLATFORMS, OPTIONS_CONFIG, CONF_DEVICE_ADDR, CONF_GATEWAY_IP
from .leelen.api.HttpApi import HttpApi
from .service import LeelenService

_LOGGER = logging.getLogger(__name__)


async def _options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """选项保存后自动重载集成:「保存即生效」(连接方式/网关IP/关联等变更无需手动 Reload)。

    reload 会走 unload→setup 重建连接与实体,短暂断开重连(秒级)。
    """
    await hass.config_entries.async_reload(entry.entry_id)


async def _resolve_gateway_ip(hass: HomeAssistant, entry: ConfigEntry) -> str | None:
    """决定 LAN 连接使用的网关 IP:「options 手动配置值」优先于「dump.db 自动检测值」。

    已配置时**不再读 dump.db**:手动覆盖本来就是为「dump 里的 LAN IP 已过期/不可信」
    准备的兜底,再去读它既可能拿到过期地址,也会在 dump.db 缺失/损坏时把启动拖垮
    (那里本来是唯一的兜底手段)。未配置时才回落到 dump.db(网关 DHCP 换 IP 后
    dump 可能仍记着旧地址,此时由用户手动填写)。
    """
    manual_ip = (entry.options.get(OPTIONS_CONFIG, {}).get(CONF_GATEWAY_IP) or "").strip()
    if manual_ip:
        _LOGGER.info("网关 IP 来源:options 配置值 %s", manual_ip)
        return manual_ip

    gateway_ip = await HttpApi.get_instance(hass).query_gateway_ip()
    _LOGGER.info("网关 IP 来源:云端 dump.db 自动检测值 %s", gateway_ip)
    if not gateway_ip:
        # LAN 模式拿不到地址时 BaseConnect.connect() 只会静默不连,这里点明原因。
        _LOGGER.warning(
            "未能确定网关 IP:LAN 模式无法建立连接。请在「选项 → 网关 IP」填写网关地址"
        )
    return gateway_ip


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})
    # 注意:entry.data 含 username/password,不要整包打进日志。

    hass.data[DOMAIN].setdefault('devices', {})

    device_addr = entry.data[CONF_DEVICE_ADDR]

    all_devices = await HttpApi.get_instance(hass).refresh_devices(device_addr)
    hass.data[DOMAIN]['devices'][entry.entry_id] = all_devices

    gateway_ip = await _resolve_gateway_ip(hass, entry)

    service = LeelenService(hass, entry)

    hass.data[DOMAIN][entry.entry_id] = {
        "service": service,
        # gateway_ip 属于本 entry(多网关条目互不干扰),不再放 DOMAIN 级共享键。
        CONF_GATEWAY_IP: gateway_ip,
    }

    # 选项保存即生效:任何 options 变更 → 自动 reload 集成(连接按新 options 重建)。
    entry.async_on_unload(entry.add_update_listener(_options_updated))

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

    domain_data = hass.data.get(DOMAIN)
    if domain_data is None:
        return unload_ok

    # 停止服务并清理数据
    data = domain_data.get(entry.entry_id)
    if data is not None:
        # stop() 内部会 join 心跳/接收/线程池等后台线程,同步调用会卡死事件循环
        # (与 service.async_restart 一致,放到执行器线程执行)。
        await hass.async_add_executor_job(data["service"].stop)
        domain_data.pop(entry.entry_id)

    # 清理设备数据
    domain_data.setdefault('devices', {}).pop(entry.entry_id, None)

    # 只有当「设备表为空且不再有任何 entry 级数据」时才回收整个 DOMAIN,
    # 避免误删其他仍在运行的 entry 的 service。
    remaining_entries = [k for k in domain_data if k != 'devices']
    if not domain_data.get('devices') and not remaining_entries:
        hass.data.pop(DOMAIN)

    return unload_ok
