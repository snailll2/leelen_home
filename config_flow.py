"""Config flow for bemfa integration."""
from __future__ import annotations

import hashlib
import traceback
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import DOMAIN, OPTIONS_SELECT, CONF_PHONE, CONF_DEVICE_ADDR
from .const import (
    OPTIONS_CONFIG,
)
from .leelen.api.HttpApi import HttpApi
from .leelen.utils.LogUtils import LogUtils
from .service import LeelenService

_LOGGER = __import__("logging").getLogger(__name__)


class LeelenIntegrationConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self):
        self._phone = None

    async def async_step_user(self, user_input=None) -> FlowResult:
        """第一步：输入手机号"""
        errors = {}

        if user_input is not None:
            phone = user_input.get("phone")
            if phone and phone.isdigit() and len(phone) == 11:
                self._phone = phone
                # 模拟发送验证码（可替换为真实 API）
                try:
                    data = await HttpApi.get_instance(self.hass).VerifyCode(self._phone)
                    if data["result"] == 10026:
                        errors["phone"] = f"短信发送频率超限，请稍后重试"
                    else:
                        _LOGGER.info(f"验证码已发送到: {phone}")
                        return await self.async_step_verify()
                except Exception as e:
                    errors["phone"] = str(e)
            else:
                errors["phone"] = "invalid_phone"

            # Multiply integration instances with same uid may case unexpected results.
            # We treat the md5sum of each configured uid as unique.
            uid_md5 = hashlib.md5(user_input[CONF_PHONE].encode("utf-8")).hexdigest()
            await self.async_set_unique_id(uid_md5)
            self._abort_if_unique_id_configured()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required("phone"): str,
            }),
            errors=errors,
            description_placeholders={"desc": "请输入您的手机号"},
        )

    async def async_step_verify(self, user_input=None) -> FlowResult:
        """第二步：输入验证码"""
        errors = {}

        if user_input is not None:
            code = user_input.get("code")
            try:
                result = await HttpApi.get_instance(self.hass).code_login(code)
                if result:
                    # 登录成功，创建配置条目
                    result[CONF_PHONE] = self._phone
                    _LOGGER.info("login success")
                    return self.async_create_entry(
                        title=f"{self._phone}",
                        data=result,
                    )
                else:
                    errors["code"] = "invalid_code"
            except Exception as e:
                errors["code"] = f"登录失败：{str(e)}"
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
    """Handle a option flow for bemfa."""

    # creat or modify a sync
    _is_create: bool

    # a dict to hold syncs when create / modify one of them
    # with this map we can get it in the next step
    # _sync_dict: dict[str, Sync]

    # current sync we are creating or modifu
    # _sync: Sync

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self._sync_dict = None
        self._entry_id = config_entry.entry_id
        self._config_entry = config_entry
        self._config = (
            config_entry.options[OPTIONS_CONFIG].copy()
            if OPTIONS_CONFIG in config_entry.options
            else {}
        )

    async def async_step_init(self, user_input=None) -> FlowResult:
        """初始选项菜单，提供刷新按钮"""
        return self.async_show_menu(
            step_id="init",
            menu_options=["refresh", "cancel"],
            # description="选择操作：",
        )

    async def async_step_refresh(self, user_input=None) -> FlowResult:
        """处理设备刷新逻辑"""
        errors = {}
        try:
            device_addr = self._config_entry.data[CONF_DEVICE_ADDR]

            all_devices = await HttpApi.get_instance(self.hass).refresh_devices(device_addr)
            self.hass.data[DOMAIN]['devices'][self._entry_id] = all_devices

            all_entities = []

            device_registry = dr.async_get(self.hass)
            existing_devices = [
                (dev.identifiers, dev.name) for dev in device_registry.devices.values()
            ]

            # 添加新设备，移除已删除设备
            added = 0
            for device in all_devices:
                device_id = device.get("dev_addr")
                dev_name = device.get("dev_name")
                logic_srv_list = device.get("logic_srv")
                for logic_srv in logic_srv_list:
                    _logic_addr = logic_srv.get("logic_addr")
                    all_entities.append(f"leelen_{device_id}_{_logic_addr}")

                # if (("LEELEN_HOME", device_id), dev_name) not in existing_devices:
                #     device_registry.async_get_or_create(
                #         config_entry_id=self._config_entry.entry_id,
                #         identifiers={("LEELEN_HOME", device.get("dev_addr"))},
                #         manufacturer="LEELEN",
                #         name=device.get("dev_name"),
                #         # model=device.get("dev_type"),
                #     )
                #     added += 1

            # 获取所有本集成的实体

            current_device_ids = [device.get("dev_addr") for device in all_devices]
            removed = 0
            for dev in device_registry.devices.values():
                for identifier in dev.identifiers:
                    if identifier[0] == "LEELEN_HOME" and identifier[1] not in current_device_ids:
                        _LOGGER.info(f"移除实体 {identifier[1]}，因为设备已从数据库中删除")
                        device_registry.async_remove_device(identifier[1])
                        removed += 1
            _LOGGER.info(f"共移除 {removed} 个无效实体")

            # 删除无用实体
            entity_registry = er.async_get(self.hass)
            entities = [(entry.entity_id, entry.unique_id) for entry in entity_registry.entities.values()]
            for entity_id, unique_id in entities:
                if unique_id is not None and unique_id.startswith(
                        "leelen_") and unique_id not in all_entities:
                    entity_registry.async_remove(entity_id)

            # 触发实体的更新
            async_dispatcher_send(self.hass, "leelen_integration_device_refresh")

            # 计算添加的设备数量
            device_registry = dr.async_get(self.hass)
            existing_device_ids = []
            for dev in device_registry.devices.values():
                for identifier in dev.identifiers:
                    if identifier[0] == "LEELEN_HOME":
                        existing_device_ids.append(identifier[1])
            added = 0
            for device in all_devices:
                device_id = device.get("dev_addr")
                if device_id not in existing_device_ids:
                    added += 1

            # 计算移除的实体数量
            removed_entities = 0
            entity_registry = er.async_get(self.hass)
            entities = [(entry.entity_id, entry.unique_id) for entry in entity_registry.entities.values()]
            for entity_id, unique_id in entities:
                if unique_id is not None and unique_id.startswith(
                        "leelen_") and unique_id not in all_entities:
                    removed_entities += 1

            # 提示刷新结果
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
        except Exception as e:
            traceback.print_exc()
            LogUtils.e(e)
            errors["base"] = str(e)

        return self.async_show_form(
            step_id="refresh",
            data_schema=vol.Schema({}),
            errors=errors,
        )

    async def async_step_refresh_result(self, user_input=None) -> FlowResult:
        return self.async_abort(reason="refresh_success")


    async def async_step_cancel(self, user_input=None) -> FlowResult:
        """处理取消操作"""
        return self.async_create_entry(title="操作已取消", data={})

    #
    async def async_step_create_sync(
            self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Create a hass-to-bemfa sync."""
        if user_input is not None:
            self._sync = self._sync_dict[user_input[OPTIONS_SELECT]]
            return await self._async_step_sync_config()

    #
    async def async_step_modify_sync(
            self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Modify a hass-to-bemfa sync."""

        self._sync_dict = {}

        if not bool(self._sync_dict):
            return self.async_show_form(step_id="empty", last_step=False)

    #
    async def _async_step_sync_config(self) -> FlowResult:
        """Set details of a hass-to-bemfa sync."""
        if self._sync.topic in self._config:
            self._sync.config = self._config[self._sync.topic]

        return self.async_show_form(
            step_id=self._sync.get_config_step_id(),
            data_schema=vol.Schema(self._sync.generate_details_schema()),
        )

    async def async_step_destroy_sync(
            self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Destroy hass-to-bemfa sync(s)"""

        return self.async_show_form(step_id="empty", last_step=False)

    def _get_service(self) -> LeelenService:
        return self.hass.data[DOMAIN].get(self._entry_id)["service"]
