"""Shared polling and controller command handling."""
from datetime import timedelta
import asyncio
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
        self.control_lock = asyncio.Lock()

    async def _async_update_data(self):
        async with self.control_lock:
            return await self._read_data()

    async def _read_data(self):
        try:
            await self._verify_identity()
            status = await self.client.read("status")
            statistic_paths = ["dev", "pixData", "pixPwrOuts"]
            config_paths = ["pix.colorType", "operIf"]
            if self.client.constants.get("dev", {}).get("auxPorts", 0):
                statistic_paths.append("auxData")
                config_paths.append("auxPort.mode")
            stats = await self.client.read("statistic", statistic_paths)
            config = await self.client.read("config", config_paths)
            if time.monotonic() - self.files_updated >= 60:
                try:
                    self.files = await self.client.files()
                    self.files_updated = time.monotonic()
                except PixLiteError as err:
                    if err.code == 14:  # No SD card: monitoring still works.
                        self.files = []
                    elif err.code != 10:  # Recording/formatting can prohibit listing.
                        raise
                    self.files_updated = time.monotonic()
            return {"status": status, "statistic": stats, "files": list(self.files), "config": config}
        except InvalidAuth as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except PixLiteError as err:
            raise UpdateFailed(str(err)) from err

    async def command(self, name, params=None):
        await self.commands([(name, params)])

    async def _verify_identity(self):
        """Check the entry identity before accepting readings or sending controls."""
        await self.client.verify_identity(self.config_entry.unique_id)

    async def commands(self, commands):
        """Keep multi-request light actions together; do not retry output changes."""
        try:
            async with self.control_lock:
                for name, params in commands:
                    await self._verify_identity()
                    await self.client.request(name, params)
        except PixLiteError as err:
            # An earlier command may have succeeded; reconcile partial success.
            await self.async_refresh()
            raise HomeAssistantError(str(err)) from err
        await self.async_refresh()
