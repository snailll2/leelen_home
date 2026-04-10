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

from .const import DOMAIN, OPTIONS_SELECT, CONF_PHONE, CONF_DEVICE_ADDR, OPTIONS_CONFIG
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
                    _LOGGER.info("登录成功: %s", self._phone)
                    return self.async_create_entry(
                        title=self._phone,
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
        self._config = dict(config_entry.options.get(OPTIONS_CONFIG, {}))
        self._refresh_stats: dict[str, str] = {}

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """初始选项菜单，提供刷新按钮"""
        return self.async_show_menu(
            step_id="init",
            menu_options=["refresh"],
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
                f"leelen_{device.get('dev_addr')}_{logic_srv.get('logic_addr')}"
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
                    # 从 unique_id 提取设备ID: leelen_{dev_addr}_{logic_addr}
                    parts = entry.unique_id.split("_")
                    if len(parts) >= 2 and parts[0] == "leelen":
                        existing_device_ids.add(parts[1])

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
