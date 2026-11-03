"""Test measurement values, organization, and registry behavior."""

from unittest.mock import MagicMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.advatek_pixlite.api import PixLiteError
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er


@pytest.mark.usefixtures("init_integration")
@pytest.mark.parametrize(
    ("key", "expected"),
    [
        ("temperature", "32.5"),
        ("bank_1_voltage", "24.1"),
        ("output_1_status", "Good"),
        ("output_2_status", "Inactv"),
        ("mode", "live"),
    ],
)
async def test_sensor_values(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    key: str,
    expected: str,
) -> None:
    """Expose measurements and playback state using persistent entity identities."""
    entity_id = entity_registry.async_get_entity_id(
        "sensor", "advatek_pixlite", f"aabbccddeeff_{key}"
    )
    assert entity_id is not None
    assert hass.states.get(entity_id).state == expected


@pytest.mark.usefixtures("init_integration")
@pytest.mark.parametrize(
    "key",
    [
        "cpu",
        "input_rate",
        "output_rate",
        "output_1_current",
        "output_1_voltage",
        "file",
    ],
)
async def test_secondary_sensors_disabled_by_default(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    key: str,
) -> None:
    """Keep secondary measurements available without enabling them automatically."""
    entity_id = entity_registry.async_get_entity_id(
        "sensor", "advatek_pixlite", f"aabbccddeeff_{key}"
    )
    assert entity_id is not None
    assert (
        entity_registry.async_get(entity_id).disabled_by
        is er.RegistryEntryDisabler.INTEGRATION
    )
    assert hass.states.get(entity_id) is None


@pytest.mark.usefixtures("init_integration")
async def test_health_category_and_channel_names(
    entity_registry: er.EntityRegistry,
) -> None:
    """Group hardware diagnostics and translate channel labels consistently."""
    entity_id = entity_registry.async_get_entity_id(
        "sensor", "advatek_pixlite", "aabbccddeeff_bank_1_voltage"
    )
    entry = entity_registry.async_get(entity_id)
    assert entry.entity_category is EntityCategory.DIAGNOSTIC
    assert entry.original_name == "Bank 1 voltage"


async def test_unsupported_output_sensors_not_created(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Only create per-output sensors when the hardware supplies their measurements."""
    mock_client.constants["dev"].update(pwrOut=False, pwrPixVolts=False)
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    assert (
        entity_registry.async_get_entity_id(
            "sensor", "advatek_pixlite", "aabbccddeeff_output_1_current"
        )
        is None
    )
    assert (
        entity_registry.async_get_entity_id(
            "sensor", "advatek_pixlite", "aabbccddeeff_output_1_status"
        )
        is None
    )


@pytest.mark.usefixtures("init_integration")
async def test_poll_failure_and_recovery(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Mark sensors unavailable on a controller error and restore them after recovery."""
    entity_id = entity_registry.async_get_entity_id(
        "sensor", "advatek_pixlite", "aabbccddeeff_temperature"
    )
    read = mock_client.read.side_effect
    mock_client.read.side_effect = PixLiteError("Offline")
    await mock_config_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == "unavailable"
    mock_client.read.side_effect = read
    await mock_config_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == "32.5"


@pytest.mark.usefixtures("init_integration")
async def test_missing_measurement_is_unknown(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Keep a supported sensor registered when a measurement is temporarily missing."""
    entity_id = entity_registry.async_get_entity_id(
        "sensor", "advatek_pixlite", "aabbccddeeff_temperature"
    )
    mock_client.objects["statistic"]["dev"]["temp"]["current"] = None
    await mock_config_entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == "unknown"


async def test_existing_enabled_entity_and_custom_name_preserved(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: MagicMock,
    entity_registry: er.EntityRegistry,
) -> None:
    """Preserve an existing user's entity name and enabled state."""
    mock_config_entry.add_to_hass(hass)
    entry = entity_registry.async_get_or_create(
        "sensor",
        "advatek_pixlite",
        "aabbccddeeff_cpu",
        config_entry=mock_config_entry,
        suggested_object_id="garden_cpu",
        disabled_by=None,
    )
    entity_registry.async_update_entity(entry.entity_id, name="My CPU")
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    entry = entity_registry.async_get(entry.entity_id)
    assert entry.name == "My CPU"
    assert entry.disabled_by is None
    assert hass.states.get(entry.entity_id).state == "7.0"
