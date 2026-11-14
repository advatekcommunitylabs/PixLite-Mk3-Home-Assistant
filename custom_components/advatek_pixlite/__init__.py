"""Advatek PixLite Mk3 integration."""

from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import InvalidAuth, PixLiteClient, PixLiteError
from .const import PLATFORMS
from .coordinator import PixLiteCoordinator
from .discovery import get_discovery


async def async_setup_entry(hass, entry):
    client = PixLiteClient(async_get_clientsession(hass), **entry.data)
    try:
        await client.initialize()
    except InvalidAuth as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except PixLiteError as err:
        raise ConfigEntryNotReady(str(err)) from err
    if client.unique_id != entry.unique_id:
        raise ConfigEntryNotReady(
            "A different controller is using this address; reconfigure the entry"
        )
    coordinator = PixLiteCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    get_discovery(hass).async_start(entry.entry_id)
    return True


async def async_unload_entry(hass, entry):
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    await get_discovery(hass).async_stop(entry.entry_id)
    return True
