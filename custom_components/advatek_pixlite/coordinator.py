"""Shared polling and controller command handling."""
from datetime import timedelta
import logging
import time

from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import InvalidAuth, PixLiteError


class PixLiteCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry, client):
        super().__init__(hass, logging.getLogger(__name__), name=entry.title,
                         config_entry=entry, update_interval=timedelta(seconds=10))
        self.client = client
        self.files = []
        self.files_updated = 0

    async def _async_update_data(self):
        try:
            status = await self.client.read("status")
            stats = await self.client.read("statistic", ["dev", "pixData", "pixPwrOuts"])
            if time.monotonic() - self.files_updated >= 60:
                try:
                    self.files = await self.client.files()
                    self.files_updated = time.monotonic()
                except PixLiteError as err:
                    if err.code == 14:  # No SD card: monitoring still works.
                        self.files = []
                    elif err.code != 10:  # Recording/formatting can prohibit listing.
                        raise
            return {"status": status, "statistic": stats, "files": list(self.files)}
        except InvalidAuth as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except PixLiteError as err:
            raise UpdateFailed(str(err)) from err

    async def command(self, name, params=None):
        try:
            await self.client.request(name, params)
        except PixLiteError as err:
            raise HomeAssistantError(str(err)) from err
        await self.async_request_refresh()
