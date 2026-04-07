"""Support for bemfa service."""
from __future__ import annotations

from types import MappingProxyType

from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import CoreState, Event, HomeAssistant

from .const import CONF_USERNAME, CONF_DEVICE_ADDR, CONF_ACCOUNT_ID, CONF_PASSWORD,CONF_GATEWAY_IP,DOMAIN
from .leelen.HeartbeatService import HeartbeatService
from .leelen.entity.GatewayInfo import GatewayInfo
from .leelen.entity.User import User
from .leelen.utils.LogUtils import LogUtils


class LeelenService:

    def __init__(self, hass: HomeAssistant, config: MappingProxyType) -> None:
        """Initialize."""
        self._hass = hass
        self._config = config
        HeartbeatService.get_instance().hass = hass

    #
    async def async_start(self, config: dict[str, dict[str, str]]) -> None:
        User.get_instance().set_account_id(self._config.get(CONF_ACCOUNT_ID))
        User.get_instance().set_username(self._config.get(CONF_USERNAME))
        User.get_instance().set_password(self._config.get(CONF_PASSWORD))
        GatewayInfo.get_instance().set_gateway_desc(self._config.get(CONF_DEVICE_ADDR))
        GatewayInfo.get_instance().set_lan_address_ip(self._hass.data[DOMAIN].get(CONF_GATEWAY_IP))

        """Start the servcie, called when component starts."""
        LogUtils.i(f"{LeelenService.__name__} start async_start")

        def _start(event: Event | None = None):
            HeartbeatService.get_instance().lan_conn_create()
            LogUtils.i(f"{LeelenService.__name__} start HeartbeatService")
            

        if self._hass.state == CoreState.running:
            _start()
        else:
            # for situations when hass restarts
            self._hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _start)
        
        await self._hass.services.async_call(
                "persistent_notification", 
                "create", 
                {"message": f"网关{self._config.get(CONF_DEVICE_ADDR)} ({self._hass.data[DOMAIN].get(CONF_GATEWAY_IP)}) 本地连接状态: 已连接", "title": "立林网关连接状态"}
            )

    def stop(self) -> None:
        """Stop the service, called when component stops."""

    async def async_restart(self):
        """重启服务"""
        LogUtils.i(f"{LeelenService.__name__} restarting")
        
        # 1. 停止当前服务
        self.stop()
        
        # 2. 重置心跳服务
        HeartbeatService.get_instance().reset_and_restart()
        
        # 3. 重新启动服务
        await self.async_start({})
        
        LogUtils.i(f"{LeelenService.__name__} restart completed")
