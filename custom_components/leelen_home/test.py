"""Support for Leelen service."""
from __future__ import annotations



from leelen.HeartbeatService import HeartbeatService
from leelen.entity.GatewayInfo import GatewayInfo
from leelen.entity.User import User
from leelen.utils.LogUtils import LogUtils

User.get_instance().set_account_id(1741108)
User.get_instance().set_username("9999018811933217")
User.get_instance().set_password("3d242814a97678cd97a0d4fd47d33a8d")
GatewayInfo.get_instance().set_gateway_desc("031525C02D000229")
GatewayInfo.get_instance().set_lan_address_ip("192.168.50.109")
HeartbeatService.get_instance().wan_conn_reopen()

# HeartbeatService.get_instance().reset_and_restart()


