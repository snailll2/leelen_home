"""Config flow for Leelen Home integration."""
from __future__ import annotations

import hashlib
import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import DOMAIN, OPTIONS_SELECT, CONF_PHONE, CONF_DEVICE_ADDR, OPTIONS_CONFIG, OPTIONS_LINKED_ENTITIES
from .leelen.api.HttpApi import HttpApi
from .leelen.utils.LogUtils import LogUtils

_LOGGER = logging.getLogger(__name__)


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
            except Exception as exc:
                _LOGGER.exception("发送验证码失败")
                errors["phone"] = str(exc)

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
            except Exception as exc:
                _LOGGER.exception("登录失败")
                errors["code"] = f"login_failed: {exc}"

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
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for Leelen Home."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self._entry_id = config_entry.entry_id
        self._config_entry = config_entry
        self._config = dict(config_entry.options.get(OPTIONS_CONFIG, config_entry.data.get(OPTIONS_CONFIG, {})))
        self._refresh_stats: dict[str, str] = {}

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """初始选项菜单，提供刷新按钮"""
        return self.async_show_menu(
            step_id="init",
            menu_options=["refresh", "link", "manage_links"],
        )

    async def async_step_refresh(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """处理设备刷新逻辑"""
        errors: dict[str, str] = {}
        try:
            device_addr = self._config_entry.data[CONF_DEVICE_ADDR]
            all_devices = await HttpApi.get_instance(self.hass).refresh_devices(device_addr)

            # 确保DOMAIN数据结构存在
            self.hass.data.setdefault(DOMAIN, {})
            self.hass.data[DOMAIN].setdefault("devices", {})
            self.hass.data[DOMAIN]["devices"][self._entry_id] = all_devices

            # 收集所有实体ID
            all_entities = {
                f"leelen_logic_addr_{logic_srv.get('logic_addr')}"
                for device in all_devices
                for logic_srv in device.get("logic_srv", [])
            }

            # 获取当前设备ID集合（确保都是字符串类型）
            current_device_ids = {str(device.get("dev_addr")) for device in all_devices}

            # 获取当前配置项已有的设备ID（通过检查实体的config_entry_id）
            entity_registry = er.async_get(self.hass)
            existing_device_ids = set()
            for entry in entity_registry.entities.values():
                if entry.config_entry_id == self._entry_id and entry.unique_id:
                    # 从 unique_id 提取设备ID: leelen_logic_addr_{logic_addr}
                    parts = entry.unique_id.split("_")
                    if len(parts) >= 2 and parts[0] == "leelen":
                        existing_device_ids.add(entry.unique_id)

            # 清理已删除的设备（只清理当前配置项的）
            device_registry = dr.async_get(self.hass)
            removed = 0
            for dev in list(device_registry.devices.values()):
                # 检查设备是否属于当前配置项
                dev_entry_ids = getattr(dev, 'config_entries', set())
                if self._entry_id not in dev_entry_ids:
                    continue
                for identifier in dev.identifiers:
                    if identifier[0] == "LEELEN_HOME" and str(identifier[1]) not in current_device_ids:
                        _LOGGER.info("移除设备 %s，因为已从数据库中删除", identifier[1])
                        device_registry.async_remove_device(dev.id)
                        removed += 1
                        break

            # 删除无用实体（只删除当前配置项的）
            removed_entities = 0
            for entry in list(entity_registry.entities.values()):
                if entry.config_entry_id != self._entry_id:
                    continue
                unique_id = entry.unique_id
                if unique_id and unique_id.startswith("leelen_") and unique_id not in all_entities:
                    entity_registry.async_remove(entry.entity_id)
                    removed_entities += 1

            # 触发实体更新
            async_dispatcher_send(self.hass, "leelen_integration_device_refresh")

            # 计算统计信息：新增 = 当前设备 - 已有设备
            added = len(current_device_ids - existing_device_ids)
            self._refresh_stats = {
                "total": str(len(all_devices)),
                "added": str(added),
                "removed": str(removed),
                "removed_entities": str(removed_entities)
            }
            return await self.async_step_refresh_result()
        except Exception as exc:
            _LOGGER.exception("刷新设备失败")
            LogUtils.e(exc)
            errors["base"] = str(exc)

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

    async def async_step_link(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """选择要关联的 VSwitch 设备"""
        entity_registry = er.async_get(self.hass)
        vswitch_entities = []
        self._entity_id_to_unique_id = {}

        for entry in entity_registry.entities.values():
            if entry.config_entry_id == self._entry_id and entry.unique_id and "leelen_logic_addr" in entry.unique_id:
                vswitch_entities.append((entry.unique_id, entry.original_name or entry.name))
                self._entity_id_to_unique_id[entry.unique_id] = entry.unique_id

        if not vswitch_entities:
            return self.async_show_form(
                step_id="link_no_vswitch",
                data_schema=vol.Schema({}),
                errors={"base": "no_vswitch_found"},
            )

        vswitch_options = {entity_id: name for entity_id, name in vswitch_entities}

        if user_input is not None:
            unique_id = user_input.get("vswitch_entity")
            self._selected_vswitch = self._entity_id_to_unique_id.get(unique_id, unique_id)
            return await self.async_step_select_linked()

        return self.async_show_form(
            step_id="link",
            data_schema=vol.Schema({
                vol.Required("vswitch_entity"): vol.In(vswitch_options),
            }),
        )

    async def async_step_select_linked(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """选择要关联的 HA 实体"""
        entity_registry = er.async_get(self.hass)
        device_registry = dr.async_get(self.hass)
        switch_entities = {}

        for entry in entity_registry.entities.values():
            if entry.domain in ["switch", "light", "input_boolean", "automation"]:
                entity_name = entry.name or entry.original_name or entry.entity_id
                device_name = entry.device_id and device_registry.async_get(entry.device_id)
                device_info = device_name.name_by_user or device_name.name if device_name else ""
                if device_info:
                    switch_entities[entry.entity_id] = f"[{device_info}] {entity_name} ({entry.domain})"
                else:
                    switch_entities[entry.entity_id] = f"{entity_name} ({entry.domain})"

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
                return self.async_create_entry(title="", options={OPTIONS_CONFIG: self._config})
            return await self.async_step_select_linked()

        vswitch_info = self._selected_vswitch
        vswitch_entity = entity_registry.async_get(self._selected_vswitch)
        if vswitch_entity:
            vswitch_name = vswitch_entity.name or vswitch_entity.original_name
            vswitch_info = f"{vswitch_name} ({self._selected_vswitch})"

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
        LogUtils.d(f"linked_entities: {linked_entities}")

        if not linked_entities:
            return await self.async_step_manage_links_empty()

        entity_registry = er.async_get(self.hass)
        
        if user_input is not None:
            selected = user_input.get("linked_action")
            if selected == "_add_new_":
                return await self.async_step_link()
            elif selected in linked_entities:
                self._selected_vswitch = selected
                return await self.async_step_link_actions()
            else:
                for key in linked_entities.keys():
                    entity = entity_registry.async_get(key)
                    if entity and entity.unique_id == selected: 
                        self._selected_vswitch = key
                        return await self.async_step_link_actions()
            return await self.async_step_manage_links()

        device_registry = dr.async_get(self.hass)
        linked_options = {}

        for vswitch_id, linked_id in linked_entities.items():
            vswitch_entity = entity_registry.async_get(vswitch_id)
            if not vswitch_entity:
                for entity in entity_registry.entities.values():
                    if entity.unique_id == vswitch_id:
                        vswitch_entity = entity
                        vswitch_id = entity.unique_id
                        break
            
            vswitch_name = vswitch_entity.name or vswitch_entity.original_name if vswitch_entity else vswitch_id
            vswitch_device = vswitch_entity.device_id and device_registry.async_get(vswitch_entity.device_id) if vswitch_entity else None
            vswitch_device_name = vswitch_device.name_by_user or vswitch_device.name if vswitch_device else ""
            vswitch_display = f"[{vswitch_device_name}] {vswitch_name}" if vswitch_device_name else vswitch_name

            linked_entity = entity_registry.async_get(linked_id)
            if not linked_entity:
                for entity in entity_registry.entities.values():
                    if entity.entity_id == linked_id or entity.unique_id == linked_id:
                        linked_entity = entity
                        break
            
            linked_name = linked_entity.name or linked_entity.original_name or linked_entity.entity_id if linked_entity else linked_id
            linked_device = linked_entity.device_id and device_registry.async_get(linked_entity.device_id) if linked_entity else None
            linked_device_name = linked_device.name_by_user or linked_device.name if linked_device else ""
            linked_display = f"[{linked_device_name}] {linked_name}" if linked_device_name else linked_name
            
            display_key = vswitch_entity.unique_id if vswitch_entity else vswitch_id
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

        entity_registry = er.async_get(self.hass)
        device_registry = dr.async_get(self.hass)

        vswitch_info = self._selected_vswitch
        vswitch_entity = entity_registry.async_get(self._selected_vswitch)
        if vswitch_entity:
            vswitch_name = vswitch_entity.name or vswitch_entity.original_name
            vswitch_device = vswitch_entity.device_id and device_registry.async_get(vswitch_entity.device_id)
            vswitch_device_name = vswitch_device.name_by_user or vswitch_device.name if vswitch_device else ""
            if vswitch_device_name:
                vswitch_info = f"[{vswitch_device_name}] {vswitch_name}({self._selected_vswitch})"
            else:
                vswitch_info = f"{vswitch_name} ({self._selected_vswitch})"

        linked_info = current_linked
        linked_entity = entity_registry.async_get(current_linked)
        if linked_entity:
            linked_name = linked_entity.name or linked_entity.original_name
            linked_device = linked_entity.device_id and device_registry.async_get(linked_entity.device_id)
            linked_device_name = linked_device.name_by_user or linked_device.name if linked_device else ""
            if linked_device_name:
                linked_info = f"[{linked_device_name}] {linked_name}({current_linked})"
            else:
                linked_info = f"{linked_name} ({current_linked})"

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
        entity_registry = er.async_get(self.hass)
        device_registry = dr.async_get(self.hass)
        switch_entities = {}

        for entry in entity_registry.entities.values():
            if entry.domain in ["switch", "light", "input_boolean", "automation"]:
                entity_name = entry.name or entry.original_name or entry.entity_id
                device_name = entry.device_id and device_registry.async_get(entry.device_id)
                device_info = device_name.name_by_user or device_name.name if device_name else ""
                if device_info:
                    switch_entities[entry.entity_id] = f"[{device_info}] {entity_name} ({entry.domain})"
                else:
                    switch_entities[entry.entity_id] = f"{entity_name} ({entry.domain})"    

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
                return self.async_create_entry(title="", options={OPTIONS_CONFIG: self._config})

        vswitch_info = self._selected_vswitch
        vswitch_entity = entity_registry.async_get(self._selected_vswitch)
        if vswitch_entity:
            vswitch_name = vswitch_entity.name or vswitch_entity.original_name
            vswitch_device = vswitch_entity.device_id and device_registry.async_get(vswitch_entity.device_id)
            vswitch_device_name = vswitch_device.name_by_user or vswitch_device.name if vswitch_device else ""
            if vswitch_device_name:
                vswitch_info = f"[{vswitch_device_name}] {vswitch_name}({self._selected_vswitch})"
            else:
                vswitch_info = f"{vswitch_name} ({self._selected_vswitch})"

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
                return self.async_create_entry(title="", options={OPTIONS_CONFIG: self._config})
            return await self.async_step_manage_links()

        entity_registry = er.async_get(self.hass)
        device_registry = dr.async_get(self.hass)

        vswitch_info = self._selected_vswitch
        vswitch_entity = entity_registry.async_get(self._selected_vswitch)
        if vswitch_entity:
            vswitch_name = vswitch_entity.name or vswitch_entity.original_name
            vswitch_device = vswitch_entity.device_id and device_registry.async_get(vswitch_entity.device_id)
            vswitch_device_name = vswitch_device.name_by_user or vswitch_device.name if vswitch_device else ""
            if vswitch_device_name:
                vswitch_info = f"[{vswitch_device_name}] {vswitch_name}({self._selected_vswitch})"
            else:
                vswitch_info = f"{vswitch_name} ({self._selected_vswitch})"

        linked_info = current_linked
        linked_entity = entity_registry.async_get(current_linked)
        if linked_entity:
            linked_name = linked_entity.name or linked_entity.original_name
            linked_device = linked_entity.device_id and device_registry.async_get(linked_entity.device_id)
            linked_device_name = linked_device.name_by_user or linked_device.name if linked_device else ""
            if linked_device_name:
                linked_info = f"[{linked_device_name}] {linked_name} ({current_linked})"
            else:
                linked_info = f"{linked_name} ({current_linked})"

        return self.async_show_form(
            step_id="delete_confirm",
            data_schema=vol.Schema({
                vol.Required("confirm", default="no"): vol.In({"yes": "是，删除", "no": "否，返回"}),
            }),
            description_placeholders={"vswitch_name": vswitch_info, "linked_name": linked_info},
        )
