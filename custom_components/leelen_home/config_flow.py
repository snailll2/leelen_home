"""Config flow for Leelen Home integration."""
from __future__ import annotations

import hashlib
import inspect
import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_send

from . import room_sync
from .const import (DOMAIN, CONF_PHONE, CONF_DEVICE_ADDR, OPTIONS_CONFIG, OPTIONS_LINKED_ENTITIES,
                    CONF_GATEWAY_IP, CONF_CONNECT_MODE, CONNECT_MODE_LAN, CONNECT_MODE_WAN,
                    DEFAULT_CONNECT_MODE, ENTITY_LOGIC_TYPES)
from .leelen.api.HttpApi import HttpApi
from .leelen.common.LeelenType import LogicDeviceType
from .platform_helper import SIGNAL_DEVICE_REFRESH

_LOGGER = logging.getLogger(__name__)


def _has_supported_channel(device: dict) -> bool:
    """设备是否有至少一个会被平台建出实体的逻辑通道。

    ``query_devices`` 已按 ``logic_type != 0 and srv_type != 0`` 过滤,这里只需判断
    logic_type 是否落在已启用平台接管的集合内(见 const.ENTITY_LOGIC_TYPES)。
    """
    return any(
        logic_srv.get("logic_type") in ENTITY_LOGIC_TYPES
        for logic_srv in device.get("logic_srv", [])
    )


class LeelenIntegrationConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._phone: str | None = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """第一步：输入手机号"""
        errors: dict[str, str] = {}

        if user_input is not None:
            phone = user_input.get("phone", "").strip()

            # 验证手机号格式
            if not (phone.isdigit() and len(phone) == 11):
                errors["phone"] = "invalid_phone"
                return self._show_user_form(errors)

            # 检查是否已配置
            uid_md5 = hashlib.md5(phone.encode("utf-8")).hexdigest()
            await self.async_set_unique_id(uid_md5)
            self._abort_if_unique_id_configured()

            self._phone = phone

            try:
                data = await HttpApi.get_instance(self.hass).VerifyCode(self._phone)
                if data.get("result") == 10026:
                    errors["phone"] = "sms_rate_limit"
                else:
                    _LOGGER.info("验证码已发送到: %s", phone)
                    return await self.async_step_verify()
            except Exception:
                # errors 的值必须是 translations 里的 key,不能塞原始异常文本
                _LOGGER.exception("发送验证码失败")
                errors["phone"] = "send_code_failed"

        return self._show_user_form(errors)

    def _show_user_form(self, errors: dict[str, str]) -> FlowResult:
        """显示手机号输入表单"""
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required("phone"): str,
            }),
            errors=errors,
            description_placeholders={"desc": "请输入您的手机号"},
        )

    async def async_step_verify(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """第二步：输入验证码"""
        errors: dict[str, str] = {}

        if user_input is not None:
            code = user_input.get("code", "").strip()
            try:
                result = await HttpApi.get_instance(self.hass).code_login(code)
                if result:
                    result[CONF_PHONE] = self._phone
                    device_addr = result.get(CONF_DEVICE_ADDR)
                    _LOGGER.info("登录成功: %s", self._phone)
                    return self.async_create_entry(
                        title=f"网关：{device_addr}({self._phone})",
                        data=result,
                    )
                errors["code"] = "invalid_code"
            except Exception:
                _LOGGER.exception("登录失败")
                errors["code"] = "login_failed"

        return self.async_show_form(
            step_id="verify",
            data_schema=vol.Schema({
                vol.Required("code"): str,
            }),
            errors=errors,
            description_placeholders={"desc": "输入短信验证码"},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return OptionsFlowHandler()


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for Leelen Home.

    HA 2024.11+ 会在流程启动前注入 ``self.config_entry``,不再经构造函数传参。
    """

    def __init__(self) -> None:
        self._config: dict[str, Any] = {}
        self._refresh_stats: dict[str, str] = {}
        self._sync_rooms_stats: dict[str, str] = {}

    # ---------- 通用帮助 ----------

    @staticmethod
    def _entity_names(
        entity_registry: er.EntityRegistry,
        device_registry: dr.DeviceRegistry,
        registry_entry: er.RegistryEntry,
    ) -> tuple[str, str]:
        """取 (设备名, 实体名);设备名缺失时为空串。"""
        name = registry_entry.name or registry_entry.original_name or registry_entry.entity_id
        device_name = ""
        if registry_entry.device_id:
            device = device_registry.async_get(registry_entry.device_id)
            if device:
                device_name = device.name_by_user or device.name or ""
        return device_name, name

    def _describe_entity(self, key: str, *, with_entity_id: bool = True) -> str:
        """实体统一显示名: [设备名] 实体名 (entity_id)。

        key 可能是 entity_id,也可能是 link 配置里存的 unique_id;
        实体查不到时退回原始 key。manage_links 的标签不带 entity_id 后缀。
        """
        entity_registry = er.async_get(self.hass)
        entity = entity_registry.async_get(key)
        if entity is None:
            for candidate in entity_registry.entities.values():
                if candidate.entity_id == key or candidate.unique_id == key:
                    entity = candidate
                    break
        if entity is None:
            return key

        device_registry = dr.async_get(self.hass)
        device_name, name = self._entity_names(entity_registry, device_registry, entity)
        prefix = f"[{device_name}] {name}" if device_name else name
        return f"{prefix} ({entity.entity_id})" if with_entity_id else prefix

    def _linkable_candidates(self) -> dict[str, str]:
        """可被关联的 HA 实体候选(entity_id → 显示名),link/modify 共用。"""
        entity_registry = er.async_get(self.hass)
        device_registry = dr.async_get(self.hass)
        candidates: dict[str, str] = {}
        for entry in entity_registry.entities.values():
            if entry.domain not in ("switch", "light", "input_boolean", "automation"):
                continue
            device_name, name = self._entity_names(entity_registry, device_registry, entry)
            prefix = f"[{device_name}] {name}" if device_name else name
            candidates[entry.entity_id] = f"{prefix} ({entry.domain})"
        return candidates

    def _vswitch_unique_ids(self) -> set[str]:
        """从设备库算出 V设备(ARM 类型)的 unique_id 集合。

        不能只按 unique_id 前缀过滤 —— 普通开关/灯/空调同样叫 leelen_logic_addr_*。
        """
        devices = (
            self.hass.data.get(DOMAIN, {}).get("devices", {}).get(self.config_entry.entry_id)
            or []
        )
        return {
            f"leelen_logic_addr_{srv.get('logic_addr')}"
            for dev in devices
            for srv in dev.get("logic_srv", [])
            if srv.get("logic_type") == LogicDeviceType.ARM
        }

    # ---------- 流程步骤 ----------

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """初始选项菜单，提供刷新按钮"""
        entry = self.config_entry
        # 老版本曾把 options 存在 data 里,读取时保留 data 兜底。
        self._config = dict(entry.options.get(OPTIONS_CONFIG, entry.data.get(OPTIONS_CONFIG, {})))
        return self.async_show_menu(
            step_id="init",
            menu_options=["refresh", "link", "manage_links", "gateway_ip", "sync_rooms", "connect_mode"],
        )

    async def async_step_gateway_ip(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """设置网关 LAN IP 覆盖。置空则使用云端 dump.db 自动检测值。

        背景:网关 DHCP 变更 IP 后,云端 dump.db 可能仍保留旧 LAN IP,
        导致 LAN 连接不到真实网关。允许用户手动指定网关 IP 兜底。
        """
        current = self._config.get(CONF_GATEWAY_IP, "")
        if user_input is not None:
            value = (user_input.get(CONF_GATEWAY_IP) or "").strip()
            self._config[CONF_GATEWAY_IP] = value
            return self.async_create_entry(title="", data={OPTIONS_CONFIG: self._config})

        try:
            auto = await HttpApi.get_instance(self.hass).query_gateway_ip()
        except Exception:
            # dump.db 缺失/损坏不应让这个表单打不开 —— 手动填写正是为绕开不可信的 dump 值。
            _LOGGER.warning("读取 dump.db 自动检测网关 IP 失败,可在下方手动填写", exc_info=True)
            auto = None
        return self.async_show_form(
            step_id="gateway_ip",
            data_schema=vol.Schema({
                vol.Required(CONF_GATEWAY_IP, default=current): str,
            }),
            description_placeholders={"auto_ip": auto or "未知"},
            errors={} if current else None,
        )

    async def async_step_connect_mode(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """连接方式:局域网(LAN)或互联网(WAN)。保存即生效(自动重载)。

        两种连接收的是同一个 LAN 帧,只是走的 socket 不同(LAN 直连网关 /
        WAN 过云端 PassThrough)。切换后由 update_listener 触发重载,连接自动重建。
        """
        current = self._config.get(CONF_CONNECT_MODE, DEFAULT_CONNECT_MODE)
        if user_input is not None:
            self._config[CONF_CONNECT_MODE] = user_input[CONF_CONNECT_MODE]
            return self.async_create_entry(title="", data={OPTIONS_CONFIG: self._config})

        return self.async_show_form(
            step_id="connect_mode",
            data_schema=vol.Schema({
                vol.Required(CONF_CONNECT_MODE, default=current): vol.In({
                    CONNECT_MODE_LAN: "局域网 (LAN)  — 设备在同一网段时最快",
                    CONNECT_MODE_WAN: "互联网 (WAN)  — 跨网段/异地也可用",
                }),
            }),
        )

    async def async_step_refresh(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """处理设备刷新逻辑"""
        errors: dict[str, str] = {}
        try:
            device_addr = self.config_entry.data[CONF_DEVICE_ADDR]
            all_devices = await HttpApi.get_instance(self.hass).refresh_devices(device_addr)

            # 确保DOMAIN数据结构存在
            self.hass.data.setdefault(DOMAIN, {})
            self.hass.data[DOMAIN].setdefault("devices", {})
            self.hass.data[DOMAIN]["devices"][self.config_entry.entry_id] = all_devices

            # 收集所有实体ID
            all_entities = {
                f"leelen_logic_addr_{logic_srv.get('logic_addr')}"
                for device in all_devices
                for logic_srv in device.get("logic_srv", [])
            }

            # 获取当前设备ID集合（确保都是字符串类型）
            current_device_ids = {str(device.get("dev_addr")) for device in all_devices}

            # 只有「至少有一个被已启用平台接管的逻辑通道」的设备才会建出实体,
            # 也只有建出实体才会在设备注册表里留下条目。设备库里可能存在通道被
            # query_devices 过滤掉的设备(如 srv_type=0 的双路窗帘面板),它们永远
            # 没有注册表条目;若拿全量 dev_tbl 去比,这类设备每轮都会被算成「新增」。
            entity_device_ids = {str(device.get("dev_addr")) for device in all_devices
                                 if _has_supported_channel(device)}
            no_channel = len(current_device_ids - entity_device_ids)

            # 通过设备注册表拿「已注册在新的配置项下」的 dev_addr 集合,
            # 再和当前 DB 设备去比,才能算出真正的新增设备数。
            # (旧实现拿实体 unique_id(leelen_logic_addr_x) 与 dev_addr 比较,
            # 两者永不相交 → 「新增」恒等于总数,统计失真。)
            # 用 async_entries_for_config_entry 而非 registry.devices 映射
            # (后者已弃用,HA 2027.9 起失效)。
            device_registry = dr.async_get(self.hass)
            registered_devices = dr.async_entries_for_config_entry(
                device_registry, self.config_entry.entry_id
            )
            if inspect.isawaitable(registered_devices):  # 旧版 HA 该 API 为协程
                registered_devices = await registered_devices
            existing_device_ids = {
                str(identifier[1])
                for dev in registered_devices
                for identifier in dev.identifiers
                if identifier[0] == "LEELEN_HOME"
            }

            # 清理已删除的设备（只清理当前配置项的）
            removed = 0
            for dev in registered_devices:
                for identifier in dev.identifiers:
                    if identifier[0] == "LEELEN_HOME" and str(identifier[1]) not in current_device_ids:
                        _LOGGER.info("移除设备 %s，因为已从数据库中删除", identifier[1])
                        device_registry.async_remove_device(dev.id)
                        removed += 1
                        break

            # 删除无用实体（只删除当前配置项的）
            entity_registry = er.async_get(self.hass)
            removed_entities = 0
            for entry in list(entity_registry.entities.values()):
                if entry.config_entry_id != self.config_entry.entry_id:
                    continue
                unique_id = entry.unique_id
                if unique_id and unique_id.startswith("leelen_") and unique_id not in all_entities:
                    entity_registry.async_remove(entry.entity_id)
                    removed_entities += 1

            # 触发实体更新
            async_dispatcher_send(self.hass, SIGNAL_DEVICE_REFRESH)

            # 计算统计信息：新增 = 能建实体的当前设备 - 已有设备
            added = len(entity_device_ids - existing_device_ids)
            self._refresh_stats = {
                "total": str(len(all_devices)),
                "added": str(added),
                "no_channel": str(no_channel),
                "removed": str(removed),
                "removed_entities": str(removed_entities)
            }
            return await self.async_step_refresh_result()
        except Exception:
            _LOGGER.exception("刷新设备失败")
            errors["base"] = "refresh_failed"

        return self.async_show_form(
            step_id="refresh",
            data_schema=vol.Schema({}),
            errors=errors,
        )

    async def async_step_refresh_result(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """刷新结果页面"""
        if user_input is not None:
            return self.async_create_entry(title="", data={})

        return self.async_show_form(
            step_id="refresh_result",
            data_schema=vol.Schema({}),
            description_placeholders=self._refresh_stats,
        )

    async def async_step_sync_rooms(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """手动同步房间:重下配置并把设备分配到 HA 区域(只填空,不覆盖已有区域)。"""
        if user_input is not None:
            return await self.async_step_sync_rooms_result()

        stats = await room_sync.sync_rooms_to_areas(
            self.hass, self.config_entry, re_download=True
        )
        if stats.note:
            self._sync_rooms_stats = {"error": stats.note}
            return await self.async_step_sync_rooms_error()

        self._sync_rooms_stats = room_sync.stats_to_placeholders(stats)
        return await self.async_step_sync_rooms_result()

    async def async_step_sync_rooms_result(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """同步结果页面"""
        if user_input is not None:
            return self.async_create_entry(title="", data={})

        return self.async_show_form(
            step_id="sync_rooms_result",
            data_schema=vol.Schema({}),
            description_placeholders=self._sync_rooms_stats,
        )

    async def async_step_sync_rooms_error(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """同步失败页面"""
        if user_input is not None:
            return self.async_create_entry(title="", data={})

        return self.async_show_form(
            step_id="sync_rooms_error",
            data_schema=vol.Schema({}),
            description_placeholders={"error": self._sync_rooms_stats.get("error", "")},
        )

    async def async_step_link(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """选择要关联的 V设备"""
        entity_registry = er.async_get(self.hass)
        vswitch_ids = self._vswitch_unique_ids()
        vswitch_options: dict[str, str] = {}

        for entry in entity_registry.entities.values():
            if entry.config_entry_id == self.config_entry.entry_id and entry.unique_id in vswitch_ids:
                vswitch_options[entry.unique_id] = entry.original_name or entry.name or entry.unique_id

        if not vswitch_options:
            return self.async_show_form(
                step_id="link_no_vswitch",
                data_schema=vol.Schema({}),
                errors={"base": "no_vswitch_found"},
            )

        if user_input is not None:
            self._selected_vswitch = user_input.get("vswitch_entity")
            return await self.async_step_select_linked()

        return self.async_show_form(
            step_id="link",
            data_schema=vol.Schema({
                vol.Required("vswitch_entity"): vol.In(vswitch_options),
            }),
        )

    async def async_step_select_linked(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """选择要关联的 HA 实体"""
        switch_entities = self._linkable_candidates()

        if not switch_entities:
            return self.async_show_form(
                step_id="select_linked_no_entity",
                data_schema=vol.Schema({}),
                errors={"base": "no_entity_found"},
            )

        if user_input is not None:
            linked_entity = user_input.get("linked_entity")
            if linked_entity:
                linked_entities = self._config.get(OPTIONS_LINKED_ENTITIES, {})
                linked_entities[self._selected_vswitch] = linked_entity
                self._config[OPTIONS_LINKED_ENTITIES] = linked_entities
                return self.async_create_entry(title="", data={OPTIONS_CONFIG: self._config})
            return await self.async_step_select_linked()

        vswitch_info = self._describe_entity(self._selected_vswitch)
        return self.async_show_form(
            step_id="select_linked",
            data_schema=vol.Schema({
                vol.Required("linked_entity"): vol.In(switch_entities),
            }),
            description_placeholders={"vswitch_name": vswitch_info},
        )

    async def async_step_manage_links_empty(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """显示空关联列表提示"""
        if user_input is not None:
            return await self.async_step_link()
        return self.async_show_form(
            step_id="manage_links_empty",
            data_schema=vol.Schema({}),
            description_placeholders={"count": "0"},
        )

    async def async_step_manage_links(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """管理已关联的实体列表"""
        linked_entities = self._config.get(OPTIONS_LINKED_ENTITIES, {})
        _LOGGER.debug("linked_entities: %s", linked_entities)

        if not linked_entities:
            return await self.async_step_manage_links_empty()

        if user_input is not None:
            selected = user_input.get("linked_action")
            if selected == "_add_new_":
                return await self.async_step_link()
            elif selected in linked_entities:
                self._selected_vswitch = selected
                return await self.async_step_link_actions()
            else:
                for key in linked_entities.keys():
                    entity = er.async_get(self.hass).async_get(key)
                    if entity and entity.unique_id == selected:
                        self._selected_vswitch = key
                        return await self.async_step_link_actions()
            return await self.async_step_manage_links()

        linked_options = {}
        for vswitch_id, linked_id in linked_entities.items():
            # 显示 key 保持与关联配置一致的 unique_id;标签只描述名称,不带 entity_id。
            display_key = vswitch_id
            entity = er.async_get(self.hass).async_get(vswitch_id)
            if entity:
                display_key = entity.unique_id
            vswitch_display = self._describe_entity(vswitch_id, with_entity_id=False)
            linked_display = self._describe_entity(linked_id, with_entity_id=False)
            linked_options[display_key] = f"{vswitch_display} → {linked_display}"

        linked_options["_add_new_"] = "+ 添加新的关联"

        return self.async_show_form(
            step_id="manage_links",
            data_schema=vol.Schema({
                vol.Required("linked_action"): vol.In(linked_options),
            }),
            description_placeholders={"count": str(len(linked_entities))},
        )

    async def async_step_link_actions(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """对单个关联的操作菜单"""
        linked_entities = self._config.get(OPTIONS_LINKED_ENTITIES, {})
        current_linked = linked_entities.get(self._selected_vswitch, "")

        if user_input is not None:
            action = user_input.get("action")
            if action == "modify":
                return await self.async_step_modify_linked()
            elif action == "delete":
                return await self.async_step_delete_confirm()
            elif action == "back":
                return await self.async_step_manage_links()

        vswitch_info = self._describe_entity(self._selected_vswitch)
        linked_info = self._describe_entity(current_linked)

        return self.async_show_form(
            step_id="link_actions",
            data_schema=vol.Schema({
                vol.Required("action"): vol.In({
                    "modify": "修改关联的 HA 实体",
                    "delete": "删除此关联",
                    "back": "返回",
                }),
            }),
            description_placeholders={"vswitch_name": vswitch_info, "linked_name": linked_info},
        )

    async def async_step_modify_linked(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """修改关联的 HA 实体"""
        switch_entities = self._linkable_candidates()

        if not switch_entities:
            return self.async_show_form(
                step_id="modify_linked_no_entity",
                data_schema=vol.Schema({}),
                errors={"base": "no_entity_found"},
            )

        if user_input is not None:
            linked_entity = user_input.get("linked_entity")
            if linked_entity:
                linked_entities = self._config.get(OPTIONS_LINKED_ENTITIES, {})
                linked_entities[self._selected_vswitch] = linked_entity
                self._config[OPTIONS_LINKED_ENTITIES] = linked_entities
                return self.async_create_entry(title="", data={OPTIONS_CONFIG: self._config})

        vswitch_info = self._describe_entity(self._selected_vswitch)
        return self.async_show_form(
            step_id="modify_linked",
            data_schema=vol.Schema({
                vol.Required("linked_entity"): vol.In(switch_entities),
            }),
            description_placeholders={"vswitch_name": vswitch_info},
        )

    async def async_step_delete_confirm(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """确认删除关联"""
        linked_entities = self._config.get(OPTIONS_LINKED_ENTITIES, {})
        current_linked = linked_entities.get(self._selected_vswitch, "")

        if user_input is not None:
            if user_input.get("confirm") == "yes":
                if self._selected_vswitch in linked_entities:
                    del linked_entities[self._selected_vswitch]
                    self._config[OPTIONS_LINKED_ENTITIES] = linked_entities
                return self.async_create_entry(title="", data={OPTIONS_CONFIG: self._config})
            return await self.async_step_manage_links()

        vswitch_info = self._describe_entity(self._selected_vswitch)
        linked_info = self._describe_entity(current_linked)

        return self.async_show_form(
            step_id="delete_confirm",
            data_schema=vol.Schema({
                vol.Required("confirm", default="no"): vol.In({"yes": "是，删除", "no": "否，返回"}),
            }),
            description_placeholders={"vswitch_name": vswitch_info, "linked_name": linked_info},
        )
