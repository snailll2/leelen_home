"""Data update coordinator for Leelen integration."""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


class LeelenCoordinator(DataUpdateCoordinator):
    """Coordinator to fetch data from Leelen API."""

    def __init__(self, hass: HomeAssistant) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name="leelen",
            update_interval=timedelta(seconds=30),
        )

    async def _async_update_data(self) -> None:
        """Update data from API."""
        # TODO: Implement data fetching when API supports it
        pass
