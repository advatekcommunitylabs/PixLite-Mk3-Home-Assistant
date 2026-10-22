"""Test entry setup, failure handling, and unloading."""

from unittest.mock import MagicMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.advatek_pixlite.api import PixLiteError
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant


@pytest.mark.usefixtures("init_integration")
async def test_unload_and_reload(
    hass: HomeAssistant, mock_config_entry: MockConfigEntry
) -> None:
    """Unload sensor listeners and reload the controller entry."""
    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    assert hass.states.get("sensor.garden_temperature") is None
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_config_entry.state is ConfigEntryState.LOADED


async def test_setup_retries_after_transport_failure(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: MagicMock,
) -> None:
    """Retry an entry that cannot initially read the controller."""
    mock_client.initialize.side_effect = PixLiteError("Offline")
    mock_config_entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(mock_config_entry.entry_id)
    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY
    mock_client.initialize.side_effect = None
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert mock_config_entry.state is ConfigEntryState.LOADED
