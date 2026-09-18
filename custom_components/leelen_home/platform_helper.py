"""各平台实体的 setup/refresh 通用逻辑。

light/switch/sensor/cover/climate/text 六个平台里叠了同一段样板:
遍历 ``hass.data[DOMAIN]["devices"]`` → 按条件 new 实体 → 逐个
``subscribe_state_updates`` → ``async_add_entities``;``async_setup_entry``
里再挂一条 device_refresh 的 dispatcher,卸载时经 ``async_on_unload`` 注销。

差异只发生在「要不要为这条设备记录建实体、建哪些」,即 ``build_entities`` 回调。
本模块把样板收敛成两个入口,各平台只写工厂函数:
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN

#: 全系统统一的设备刷新信号。__init__ 或 room_sync 下载新设备后经它广播,
#: 各平台 setup 时订阅,重跑 setup_devices_from_db 补上新实体。
SIGNAL_DEVICE_REFRESH = "leelen_integration_device_refresh"


def _added_unique_ids(hass: HomeAssistant, config_entry: ConfigEntry) -> set[str]:
    """本次 HA 运行期内、本配置项已经添加过的实体 unique_id 集合。

    用途:device_refresh 会重跑 ``setup_devices_from_db`` 并为**全部**设备重建实体,
    已添加过的那些会撞 unique_id —— HA 只打一条 ERROR「does not generate unique IDs」
    然后丢弃(每次同步每台设备一行噪音日志)。据此跳过它们。

    注意**不能用实体注册表**判断:注册表跨重启持久化,启动时里面已经有上次运行留下的
    全部实体,拿它过滤会导致重启后一个实体都不创建 —— 界面上所有实体变成 unavailable
    (HA 会把注册表里有、平台却没提供的实体恢复成不可用态)。
    因此这里只在内存里记录「本次运行已添加过谁」,卸载时随 entry 数据一起丢弃。
    """
    entry_data = hass.data.setdefault(DOMAIN, {}).setdefault(config_entry.entry_id, {})
    if not isinstance(entry_data, dict):  # 防御:DOMAIN 下该键被占作他用
        return set()
    return entry_data.setdefault("entity_unique_ids", set())


async def setup_devices_from_db(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
    build_entities,
) -> list:
    """遍历设备库,建实体,订阅状态更新并添加。

    ``build_entities(device_info, config_entry)`` 返回单个实体、实体列表或 None;
    返回 None/空表不建实体(text 平台按 all_property 建,同样走这里)。
    返回本次创建的实体列表,供 async_setup_entry 做添加后的收尾。
    """
    device_list = hass.data[DOMAIN]["devices"].get(config_entry.entry_id) or []
    # 跳过本次运行已经添加过的实体(见 _added_unique_ids 的说明),新设备照常建出。
    added_ids = _added_unique_ids(hass, config_entry)
    entities = []
    for device_info in device_list:
        created = build_entities(device_info, config_entry)
        if created is None:
            continue
        if not isinstance(created, (list, tuple)):
            created = [created]
        for entity in created:
            if entity is None:
                continue
            if entity.unique_id in added_ids:
                continue
            entities.append(entity)

    # 记录本批实际要添加的 unique_id,后续 refresh 才能跳过它们。
    added_ids.update(entity.unique_id for entity in entities)

    # HA 原生状态更新订阅(取代旧 FlowRxBus 事件总线)。
    # 平台若不用订阅(text 等重属性实体),实体自带该属性即可透传。
    for entity in entities:
        subscribe = getattr(entity, "subscribe_state_updates", None)
        if subscribe is not None:
            subscribe(hass)

    async_add_entities(entities)
    return entities


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
    build_entities,
    *,
    finalize=None,
) -> None:
    """setup + 注册 device_refresh 刷新订阅。

    ``finalize(entities, hass)`` 可选,实体添加后的收尾(如 switch 的
    VSwitch 联动监听注册);refresh 重跑时的第一批新实体同样会走一次。
    """
    entities = await setup_devices_from_db(hass, config_entry, async_add_entities, build_entities)
    if finalize:
        finalize(entities, hass)

    async def handle_refresh():
        batch = await setup_devices_from_db(hass, config_entry, async_add_entities, build_entities)
        if finalize:
            finalize(batch, hass)

    # 卸载时经 async_on_unload 注销,避免 refresh 分发重复添加实体
    config_entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_DEVICE_REFRESH, handle_refresh)
    )