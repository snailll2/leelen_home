from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
)

_LOGGER = logging.getLogger(__name__)


class LeelenCoordinator(DataUpdateCoordinator):

    def __init__(self, hass: HomeAssistant, ):
        super().__init__(
            hass,
            _LOGGER,
            name="leelen api",
            update_interval=timedelta(seconds=10),
        )

    async def _async_update_data(self):
        pass
        # async with async_timeout.timeout(10):
        #     return await self.hub.deviceList()
