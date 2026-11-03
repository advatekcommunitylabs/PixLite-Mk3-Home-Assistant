"""Support for Advatek PixLite Mk3 controllers."""

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .coordinator import PixLiteConfigEntry, PixLiteCoordinator

PLATFORMS = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: PixLiteConfigEntry) -> bool:
    """Set up one controller's monitoring entities."""
    coordinator = PixLiteCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: PixLiteConfigEntry) -> bool:
    """Unload the controller's monitoring entities."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
