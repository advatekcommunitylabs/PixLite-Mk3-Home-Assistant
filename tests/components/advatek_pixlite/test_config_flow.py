"""Test connection validation and entry identity through Home Assistant."""

from unittest.mock import MagicMock

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.advatek_pixlite.api import (
    InvalidAuth,
    PixLiteError,
    UnsupportedDevice,
)
from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType


async def test_user_flow(
    hass: HomeAssistant,
    mock_client: MagicMock,
) -> None:
    """Create a controller entry after validating its connection."""
    result = await hass.config_entries.flow.async_init(
        "advatek_pixlite", context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "host": "192.0.2.10",
            "username": "admin",
            "password": "",
            "use_ssl": False,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == "aabbccddeeff"
    assert result["data"]["password"] == ""
    await hass.async_block_till_done()


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (InvalidAuth("Rejected"), "invalid_auth"),
        (UnsupportedDevice("Unsupported"), "unsupported_device"),
        (PixLiteError("Offline"), "cannot_connect"),
    ],
)
async def test_connection_error_and_recovery(
    hass: HomeAssistant,
    mock_client: MagicMock,
    error: Exception,
    expected: str,
) -> None:
    """Show controller errors and allow the same flow to recover."""
    mock_client.initialize.side_effect = error
    result = await hass.config_entries.flow.async_init(
        "advatek_pixlite", context={"source": SOURCE_USER}
    )
    data = {"host": "192.0.2.10", "username": "admin", "password": "", "use_ssl": False}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], data)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": expected}
    mock_client.initialize.side_effect = None
    result = await hass.config_entries.flow.async_configure(result["flow_id"], data)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()


async def test_invalid_host_and_recovery(
    hass: HomeAssistant, mock_client: MagicMock
) -> None:
    """Reject URLs in the host field and retain a usable setup flow."""
    result = await hass.config_entries.flow.async_init(
        "advatek_pixlite", context={"source": SOURCE_USER}
    )
    data = {
        "host": "https://192.0.2.10",
        "username": "admin",
        "password": "",
        "use_ssl": False,
    }
    result = await hass.config_entries.flow.async_configure(result["flow_id"], data)
    assert result["errors"] == {"host": "invalid_host"}
    data["host"] = "192.0.2.10"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], data)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()


async def test_duplicate_controller(
    hass: HomeAssistant,
    mock_client: MagicMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Prevent the same MAC from becoming a second controller entry."""
    mock_config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        "advatek_pixlite", context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "host": "192.0.2.10",
            "username": "admin",
            "password": "",
            "use_ssl": False,
        },
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
