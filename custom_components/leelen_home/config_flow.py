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

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """初始选项菜单，提供刷新按钮"""
        return self.async_show_menu(
            step_id="init",
            menu_options=["refresh", "cancel"],
        )

    async def async_step_refresh(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """处理设备刷新逻辑"""
        errors: dict[str, str] = {}
        try:
            device_addr = self._config_entry.data[CONF_DEVICE_ADDR]
            all_devices = await HttpApi.get_instance(self.hass).refresh_devices(device_addr)
            self.hass.data[DOMAIN]["devices"][self._entry_id] = all_devices

            # 收集所有实体ID
            all_entities = {
                f"leelen_{device.get('dev_addr')}_{logic_srv.get('logic_addr')}"
                for device in all_devices
                for logic_srv in device.get("logic_srv", [])
            }

            # 清理已删除的设备
            device_registry = dr.async_get(self.hass)
            current_device_ids = {device.get("dev_addr") for device in all_devices}
            removed = 0
            for dev in device_registry.devices.values():
                for identifier in dev.identifiers:
                    if identifier[0] == "LEELEN_HOME" and identifier[1] not in current_device_ids:
                        _LOGGER.info("移除设备 %s，因为已从数据库中删除", identifier[1])
                        device_registry.async_remove_device(dev.id)
                        removed += 1
                        break

            # 删除无用实体
            entity_registry = er.async_get(self.hass)
            removed_entities = 0
            for entry in list(entity_registry.entities.values()):
                unique_id = entry.unique_id
                if unique_id and unique_id.startswith("leelen_") and unique_id not in all_entities:
                    entity_registry.async_remove(entry.entity_id)
                    removed_entities += 1

            # 触发实体更新
            async_dispatcher_send(self.hass, "leelen_integration_device_refresh")

            # 计算统计信息
            existing_device_ids = {
                identifier[1]
                for dev in device_registry.devices.values()
                for identifier in dev.identifiers
                if identifier[0] == "LEELEN_HOME"
            }
            added = len(current_device_ids - existing_device_ids)

            return self.async_show_form(
                step_id="refresh_result",
                data_schema=vol.Schema({}),
                description_placeholders={
                    "total": str(len(all_devices)),
                    "added": str(added),
                    "removed": str(removed),
                    "removed_entities": str(removed_entities)
                },
            )
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
        return self.async_abort(reason="refresh_success")

    async def async_step_cancel(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """处理取消操作"""
        return self.async_create_entry(title="操作已取消", data={})
