"""Constants for the leelen integration."""
from typing import Final

from homeassistant.components.climate import HVACMode, FAN_AUTO, FAN_LOW, FAN_HIGH, FAN_MEDIUM

DOMAIN: Final = "leelen"

SUPPORTED_PLATFORMS: list = [
    # 'binary_sensor',
    # 'button',
    'climate',
    'cover',
    # 'event',
    # 'fan',
    # 'humidifier',
    'light',
    # 'notify',
    # 'number',
    # 'select',
    'sensor',
    'switch',
    # 'text',
    # 'vacuum',
    # 'water_heater',
]

# #### Config ####
CONF_PHONE: Final = "phone"
CONF_USERNAME: Final = "username"
CONF_PASSWORD: Final = "password"
CONF_DEVICE_ADDR: Final = "deviceAddr"
CONF_ACCOUNT_ID: Final = "accountId"
CONF_GATEWAY_IP: Final = "gateway_ip"

OPTIONS_CONFIG: Final = "config"
OPTIONS_SELECT: Final = "select"

FAN_MODE_SPEED_MAP = {
    FAN_LOW: 1,
    FAN_MEDIUM: 2,
    FAN_HIGH: 3,
    FAN_AUTO: 5
}
SPEED_FAN_MODE_MAP = {v: k for k, v in FAN_MODE_SPEED_MAP.items()}

HVAC_MODE_MAP = {
    HVACMode.FAN_ONLY: 0,
    HVACMode.HEAT: 1,
    HVACMode.COOL: 2,
    HVACMode.DRY: 3
}

MODE_HVAC_MAP = {v: k for k, v in HVAC_MODE_MAP.items()}
