"""Fixtures for controller setup and sensor state tests."""

from collections.abc import Generator
from copy import deepcopy
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Return one controller entry with a persistent MAC identity."""
    return MockConfigEntry(
        domain="advatek_pixlite",
        title="Garden",
        unique_id="aabbccddeeff",
        data={
            "host": "192.0.2.10",
            "username": "admin",
            "password": "",
            "use_ssl": False,
        },
    )


@pytest.fixture
def mock_client() -> Generator[MagicMock]:
    """Mock the controller boundary while keeping Home Assistant real."""
    client = MagicMock()
    client.unique_id = "aabbccddeeff"
    client.base_url = "http://192.0.2.10:80"
    client.version = {"nickname": "Garden"}
    client.constants = {
        "dev": {
            "macAddr": "AA-BB-CC-DD-EE-FF",
            "prodName": "PixLite A4-S Mk3",
            "prodFamilyName": "PixLite Mk3",
            "pwrBanksIn": 1,
            "pwrOut": True,
            "pwrPixVolts": True,
            "pixPorts": 2,
            "auxPorts": 0,
        },
        "ver": {"fw": "3.14.2", "hw": "1"},
    }
    client.initialize = AsyncMock(return_value=client.constants)
    client.files = AsyncMock(return_value=[])
    client.request = AsyncMock(return_value={})
    client.objects = {
        "constant": client.constants,
        "statistic": {
            "dev": {"temp": {"current": 32.5}, "cpu": 7, "bankVolt": [24100]},
            "pixData": {"inFrmRate": 40, "outFrmRate": 60},
            "pixPwrOuts": {
                "current": [1250, 0],
                "voltage": [24000, 0],
                "stat": ["Good", "Inactv"],
            },
        },
        "status": {"mode": "live"},
        "config": {"pix": {"colorType": "RGB"}, "operIf": {}},
    }

    async def read(name: str, paths: list[str] | None = None) -> dict:
        """Return a controller object without opening network connections."""
        return deepcopy(client.objects[name])

    client.read = AsyncMock(side_effect=read)
    factory = MagicMock(return_value=client)
    with (
        patch("custom_components.advatek_pixlite.PixLiteClient", factory, create=True),
        patch("custom_components.advatek_pixlite.config_flow.PixLiteClient", factory),
        patch(
            "custom_components.advatek_pixlite.coordinator.PixLiteClient",
            factory,
            create=True,
        ),
        patch("custom_components.advatek_pixlite.PLATFORMS", [Platform.SENSOR]),
    ):
        yield client


@pytest.fixture
async def init_integration(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_client: MagicMock,
) -> MockConfigEntry:
    """Set up real Home Assistant sensor entities for a simulated controller."""
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    return mock_config_entry
