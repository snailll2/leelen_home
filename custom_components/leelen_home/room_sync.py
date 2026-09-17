"""将立林网关房间配置同步到 HA 区域(area)与设备 area_id。

设计原则:
- 只填空:设备已有 area_id 的一律不覆盖(fill-gaps only)。
- room_id == 0 是「客厅」,与其他房间同等对待。设备没有任何非 0 房间
  归属时归入客厅(room 0);已有非 0 房间通道的设备按其多数通道归属。
- 顶层只用 stdlib,HA 相关 import 全部放在 async 函数内部懒加载,
  使 compute_device_room_map / SyncStats 可在无 HA 环境下直接单测。
"""
from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass
from typing import Any

LOGGER = logging.getLogger(__name__)


async def _registry_call(obj: Any, method_names: tuple[str, ...], **kwargs: Any) -> Any:
    """兼容 HA 各版本的注册表 API。

    - 方法名因版本而异(旧版 AreaRegistry 用 async_create_area,新版改名 async_create);
    - 同名方法在不同版本可能是协程也可能是同步方法(2026.x 起注册表全部同步)。
    """
    method = None
    for name in method_names:
        if hasattr(obj, name):
            method = getattr(obj, name)
            break
    if method is None:
        raise AttributeError(f"{type(obj).__name__} 缺少 {'/'.join(method_names)}")
    result = method(**kwargs)
    if inspect.isawaitable(result):
        return await result
    return result


@dataclass
class SyncStats:
    """一次房间→区域同步的统计结果。note 非空表示出错(处理过程内异常不抛出)。"""

    rooms: int = 0
    areas_created: int = 0
    devices_assigned: int = 0
    devices_skipped_no_room: int = 0
    devices_skipped_has_area: int = 0
    devices_skipped_no_device_entry: int = 0
    devices_skipped_no_area: int = 0
    note: str = ""


def _to_int(value: Any) -> int:
    """宽松转 int;None/无法解析一律视为 0。"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def compute_device_room_map(devices: list[dict]) -> dict[int, int]:
    """返回 {dev_addr: 多数房间 room_id}。

    与平台实体消费的是同一份 query_devices 列表(每个 device 的 logic_srv
    已含 room_id 列)。每台设备的房间取其逻辑通道中出现最多的非 0 room_id
    (平票取最小 room_id,确定性便于单测);设备所有通道都是 0 时归入
    「客厅」(room 0)。无任何逻辑通道或 dev_addr 非法的设备不产生键。
    """
    result: dict[int, int] = {}
    for device in devices:
        counter: dict[int, int] = {}
        for logic_srv in device.get("logic_srv") or []:
            room_id = _to_int(logic_srv.get("room_id")) if isinstance(logic_srv, dict) else 0
            counter[room_id] = counter.get(room_id, 0) + 1
        if not counter:
            continue
        # 有非 0 房间时按非 0 多数票归属(刻意配置优先于默认值 0);全 0 → 客厅
        nonzero = {room_id: count for room_id, count in counter.items() if room_id != 0}
        if nonzero:
            room_id = min(nonzero, key=lambda r: (-nonzero[r], r))
        else:
            room_id = 0
        dev_addr = _to_int(device.get("dev_addr"))
        if dev_addr == 0:
            continue
        result[dev_addr] = room_id
    return result


def stats_to_placeholders(stats: SyncStats) -> dict[str, str]:
    """把统计字段转成 description_placeholders 可用的字符串 dict。"""
    return {
        "rooms": str(stats.rooms),
        "areas_created": str(stats.areas_created),
        "devices_assigned": str(stats.devices_assigned),
        "devices_skipped_no_room": str(stats.devices_skipped_no_room),
        "devices_skipped_has_area": str(stats.devices_skipped_has_area),
        "devices_skipped_no_device_entry": str(stats.devices_skipped_no_device_entry),
        "devices_skipped_no_area": str(stats.devices_skipped_no_area),
    }


async def sync_rooms_to_areas(hass, entry, *, re_download: bool = False) -> SyncStats:
    """执行一次房间→区域同步,返回统计。任何异常都被捕获并写入 stats.note。

    - re_download=True(手动按钮):先重新下载并解析 dump.db;
    - 自动路径(每次 setup):复用 setup 时已写入 hass.data 的设备列表。
    """

    from homeassistant.helpers import area_registry as ars  # noqa: PLC0415
    from homeassistant.helpers import device_registry as dr  # noqa: PLC0415

    from .const import CONF_DEVICE_ADDR, DOMAIN  # noqa: PLC0415
    from .leelen.api.HttpApi import HttpApi  # noqa: PLC0415

    stats = SyncStats()
    try:
        # 1. 重下配置(仅手动路径)
        if re_download:
            device_addr = entry.data[CONF_DEVICE_ADDR]
            devices = await HttpApi.get_instance(hass).refresh_devices(device_addr)
            if devices is not None:
                hass.data.setdefault(DOMAIN, {}).setdefault("devices", {})[entry.entry_id] = devices

        # 2. 房间表(含 room_id 0 的「客厅」)
        rooms = await HttpApi.get_instance(hass).query_rooms()
        room_names: dict[int, str] = {
            r["room_id"]: r.get("room_name") for r in rooms if r.get("room_name")
        }
        stats.rooms = len(room_names)

        # 3. 设备→房间映射(复用平台消费的同一份设备列表)
        devices = hass.data.get(DOMAIN, {}).get("devices", {}).get(entry.entry_id) or []
        dev_room_map = compute_device_room_map(devices)
        stats.devices_skipped_no_room = len(devices) - len(dev_room_map)

        # 注意:DR 的 async_get 是同步,AR 的 async_get 可能是协程(2026.x 用
        # @singleton+@lru_cache 返回协程),统一走 _registry_call 兼容。
        drs = await _registry_call(dr, ("async_get",), hass=hass)
        ars_reg = await _registry_call(ars, ("async_get",), hass=hass)
        room_area: dict[int, str | None] = {}  # room_id -> area_id;None=该房间无可用区域

        async def _resolve_device(dev_addr: int):
            """按 LEELEN_HOME 标识解析 HA 设备。标识值可能是 int 或 str,逐个尝试。"""
            for candidate in (dev_addr, str(dev_addr)):
                identifier = ("LEELEN_HOME", candidate)
                # 新版注册表:标识不再跨 config entry 唯一,async_get_device 已弃用,
                # 改 async_get_device_by_identifier(2027.8 起移除);旧版仍用
                # async_get_device(identifiers=set)。两者参数形态不同,分开传参。
                if hasattr(drs, "async_get_device_by_identifier"):
                    device = await _registry_call(
                        drs, ("async_get_device_by_identifier",), identifier=identifier
                    )
                else:
                    device = await _registry_call(
                        drs, ("async_get_device",), identifiers={identifier}
                    )
                if device is not None:
                    return device
            # 兜底:类型漂移时按 str 值手动匹配(devices 在新旧版注册表里都暴露,再退私有表)
            devices_map = getattr(drs, "devices", None) or getattr(drs, "_device_data", None)
            for device in devices_map.values():
                for dtype, dval in device.identifiers:
                    if dtype == "LEELEN_HOME" and str(dval) == str(dev_addr):
                        return device
            return None

        async def _ensure_area(room_id: int) -> str | None:
            """按房间名取/建 HA 区域;房间名缺失时返回 None。"""
            if room_id in room_area:
                return room_area[room_id]
            area_id: str | None = None
            name = room_names.get(room_id)
            if name:
                area = await _registry_call(ars_reg, ("async_get_area_by_name",), name=name)
                if area is None:
                    area = await _registry_call(
                        ars_reg, ("async_create", "async_create_area"), name=name
                    )
                    stats.areas_created += 1
                # AreaEntry 主键旧版叫 area_id,2026.x 改名为 id
                area_id = getattr(area, "id", None) or getattr(area, "area_id", None)
            else:
                LOGGER.warning("room_sync: room_id %s 在 room_tbl 无行或房间名为空,跳过", room_id)
            room_area[room_id] = area_id
            return area_id

        # 4. 只填空:设备已有 area_id 的不覆盖
        for dev_addr, room_id in dev_room_map.items():
            device = await _resolve_device(dev_addr)
            if device is None:
                stats.devices_skipped_no_device_entry += 1
                continue
            if device.area_id:
                stats.devices_skipped_has_area += 1
                continue
            area_id = await _ensure_area(room_id)
            if area_id is None:
                stats.devices_skipped_no_area += 1
                continue
            LOGGER.info("room_sync: 设备 %s → 区域 %s (room_id %s)", dev_addr, area_id, room_id)
            await _registry_call(
                drs, ("async_update_device",), device_id=device.id, area_id=area_id
            )
            stats.devices_assigned += 1

    except Exception as exc:  # noqa: BLE001 - 自动路径绝不能因同步失败而炸 setup
        LOGGER.exception("room_sync: 同步失败")
        stats.note = f"同步失败:{exc}"

    return stats


async def run_background_sync(hass, entry) -> None:
    """后台自动同步入口:异常已收敛进 SyncStats.note,这里再做一层保险。"""
    try:
        stats = await sync_rooms_to_areas(hass, entry)
        LOGGER.info(
            "room_sync: 自动房间→区域同步完成,房间 %s / 新建区域 %s / 分配设备 %s / "
            "跳过(无房间) %s / 跳过(已有区域) %s",
            stats.rooms,
            stats.areas_created,
            stats.devices_assigned,
            stats.devices_skipped_no_room,
            stats.devices_skipped_has_area,
        )
    except Exception:  # noqa: BLE001
        LOGGER.exception("room_sync: 后台同步异常")