"""Poll controller measurements for the sensor platform."""

from datetime import timedelta
import logging
from typing import Any, TypedDict

from advatek_pixlite_client import InvalidAuth, PixLiteClient, PixLiteError

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class PixLiteData(TypedDict):
    """Latest controller measurements and playback status."""

    statistic: dict[str, Any]
    status: dict[str, Any]


type PixLiteConfigEntry = ConfigEntry[PixLiteCoordinator]


class PixLiteCoordinator(DataUpdateCoordinator[PixLiteData]):
    """Share one polling snapshot among the controller's sensors."""

    config_entry: PixLiteConfigEntry

    def __init__(self, hass: HomeAssistant, entry: PixLiteConfigEntry) -> None:
        """Initialize the controller client and polling interval."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=10),
        )
        self.client = PixLiteClient(async_get_clientsession(hass), **entry.data)

    async def _async_setup(self) -> None:
        """Read controller capabilities before adding sensors."""
        try:
            await self.client.initialize()
        except InvalidAuth as err:
            raise ConfigEntryAuthFailed from err
        except PixLiteError as err:
            raise UpdateFailed(str(err)) from err
        if self.client.unique_id != self.config_entry.unique_id:
            raise ConfigEntryError("Controller MAC address does not match the entry")

    async def _async_update_data(self) -> PixLiteData:
        """Read controller identity, measurements, and playback status."""
        try:
            await self.client.verify_identity(self.config_entry.unique_id)
            return {
                "statistic": await self.client.read(
                    "statistic", ["dev", "pixData", "pixPwrOuts"]
                ),
                "status": await self.client.read("status"),
            }
        except InvalidAuth as err:
            raise ConfigEntryAuthFailed from err
        except PixLiteError as err:
            raise UpdateFailed(str(err)) from err
