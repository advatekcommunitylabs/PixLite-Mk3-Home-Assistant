"""Test entry setup, failure handling, and unloading."""

from unittest.mock import MagicMock

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.advatek_pixlite.api import PixLiteError
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util


@pytest.mark.usefixtures("init_integration")
async def test_unload_and_reload(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Unload sensor listeners and reload the controller entry."""
    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    assert hass.states.get("sensor.garden_temperature").state == "unavailable"
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_config_entry.state is ConfigEntryState.LOADED


async def test_setup_retries_after_transport_failure(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: MagicMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Retry an entry that cannot initially read the controller."""
    mock_client.initialize.side_effect = PixLiteError("Offline")
    mock_config_entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(mock_config_entry.entry_id)
    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY
    mock_client.initialize.side_effect = None
    freezer.tick(10)
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done(wait_background_tasks=True)
    assert mock_config_entry.state is ConfigEntryState.LOADED
