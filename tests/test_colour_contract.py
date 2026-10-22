"""Exercise colour entities with real Home Assistant types and service routing."""

from copy import deepcopy
from datetime import timedelta
import logging
from types import MappingProxyType, SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from custom_components.advatek_pixlite.coordinator import PixLiteCoordinator
from custom_components.advatek_pixlite.light import PixLiteLight
from custom_components.advatek_pixlite.number import SolidColorChannel
from homeassistant import loader
from homeassistant.components import light
from homeassistant.config_entries import ConfigEntries, ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry, entity_registry
from homeassistant.helpers.entity_platform import EntityPlatform
from homeassistant.setup import async_setup_component


@pytest_asyncio.fixture
async def colour_runtime(tmp_path):
    """Create real entity platforms with an in-memory controller boundary."""
    hass = HomeAssistant(str(tmp_path))
    loader.async_setup(hass)
    device_registry.async_setup(hass)
    await device_registry.async_load(hass)
    await entity_registry.async_load(hass)
    hass.config_entries = ConfigEntries(hass, {})
    entry = ConfigEntry(
        data={},
        discovery_keys=MappingProxyType({}),
        domain="advatek_pixlite",
        minor_version=1,
        options={},
        source="user",
        subentries_data=None,
        title="Garden",
        unique_id="aabbccddeeff",
        version=1,
        state=ConfigEntryState.LOADED,
    )
    hass.config_entries._entries[entry.entry_id] = entry
    client = SimpleNamespace(
        unique_id="aabbccddeeff",
        version={"nickname": "Garden"},
        constants={"dev": {"prodName": "PixLite A4-S Mk3"}},
        base_url="http://192.0.2.10",
    )
    data = {
        "config": {"pix": {"colorType": "RGBWX"}, "operIf": {}},
        "status": {
            "mode": "playback",
            "params": {
                "op": "Color",
                "color": [100, 200, 300, 400, 500],
                "colorRes": "16Bit",
            },
            "outInt": [{"out": "Pix", "progPri": "Hi", "fc": [0, 128]}],
        },
        "statistic": {},
        "files": [],
    }

    async def read(name, paths=None):
        return deepcopy(data[name])

    async def request(name, params):
        if name == "modePlayback":
            data["status"] = {
                **data["status"],
                "mode": "playback",
                "params": deepcopy(params),
            }
        elif name == "progInt":
            data["status"]["outInt"][0]["fc"][1] = params["item"][0]["fc"]

    client.read = AsyncMock(side_effect=read)
    client.request = AsyncMock(side_effect=request)
    coordinator = PixLiteCoordinator(hass, entry, client)
    coordinator.data = deepcopy(data)

    async def refresh():
        coordinator.async_set_updated_data(deepcopy(data))

    coordinator.async_request_refresh = refresh
    platforms = []
    for domain in ("light", "number"):
        assert await async_setup_component(hass, domain, {})
        platforms.append(
            EntityPlatform(
                hass=hass,
                logger=logging.getLogger(__name__),
                domain=domain,
                platform_name="advatek_pixlite",
                platform=None,
                scan_interval=timedelta(seconds=30),
                entity_namespace=None,
            )
        )
        platforms[-1].config_entry = entry
    pixels = PixLiteLight(coordinator)
    pixels.entity_id = "light.garden_pixels"
    channel = SolidColorChannel(coordinator, 4)
    channel.entity_id = "number.garden_x"
    channel._attr_entity_registry_enabled_default = True
    await platforms[0].async_add_entities([pixels])
    await platforms[1].async_add_entities([channel])
    await hass.async_block_till_done()
    yield hass, coordinator, client, data, pixels, channel
    for platform in platforms:
        await platform.async_reset()
    await coordinator.async_shutdown()
    await hass.async_stop()


async def test_rgbwx_services_preserve_other_channels(colour_runtime):
    """Route RGBW and raw X service calls through Home Assistant's actual schemas."""
    hass, coordinator, client, data, pixels, channel = colour_runtime
    await hass.services.async_call(
        "light",
        "turn_on",
        {
            "entity_id": pixels.entity_id,
            "rgbw_color": [1, 2, 3, 4],
            "transition": 1.25,
        },
        blocking=True,
    )
    assert data["status"]["params"]["color"] == [257, 514, 771, 1028, 500]
    assert data["status"]["params"]["fadeMs"] == 1250
    await hass.services.async_call(
        "number",
        "set_value",
        {
            "entity_id": channel.entity_id,
            "value": 12345,
        },
        blocking=True,
    )
    assert data["status"]["params"]["color"] == [257, 514, 771, 1028, 12345]
    assert data["status"]["outInt"][0]["fc"][1] == 128
    state = hass.states.get(pixels.entity_id)
    assert state.attributes["supported_color_modes"] == [light.ColorMode.RGBW]
    assert state.attributes["x_channel_16bit"] == 12345
    assert hass.states.get(channel.entity_id).state == "12345"


@pytest.mark.parametrize(
    "kind,attribute,value,expected",
    [
        ("RGB", "rgb_color", [1, 2, 3], [257, 514, 771]),
        ("RGBW", "rgbw_color", [1, 2, 3, 4], [257, 514, 771, 1028]),
        ("RGBWX", "rgb_color", [255, 0, 0], [65535, 0, 0, 0, 500]),
    ],
)
async def test_controller_type_and_ha_colour_conversion(
    colour_runtime, kind, attribute, value, expected
):
    """Use HA's conversion into the advertised RGB/RGBW service format."""
    hass, coordinator, client, data, pixels, channel = colour_runtime
    data["config"]["pix"]["colorType"] = kind
    data["status"]["params"]["color"] = [100, 200, 300, 400, 500][: len(expected)]
    await coordinator.async_request_refresh()
    await hass.services.async_call(
        "light",
        "turn_on",
        {
            "entity_id": pixels.entity_id,
            attribute: value,
        },
        blocking=True,
    )
    assert data["status"]["params"]["color"] == expected


async def test_service_rejects_changed_configuration_before_writing(colour_runtime):
    """Reject a stale picker request if the controller's new type is unknown."""
    hass, coordinator, client, data, pixels, channel = colour_runtime
    data["config"]["pix"].pop("colorType")
    with pytest.raises(HomeAssistantError, match="missing or unsupported"):
        await hass.services.async_call(
            "light",
            "turn_on",
            {
                "entity_id": pixels.entity_id,
                "rgbw_color": [1, 2, 3, 4],
            },
            blocking=True,
        )
    client.request.assert_not_awaited()
    state = hass.states.get(pixels.entity_id)
    assert state.attributes["supported_color_modes"] == [light.ColorMode.BRIGHTNESS]
    assert hass.states.get(channel.entity_id).state == "unavailable"


@pytest.mark.parametrize("value", [0, 65535])
async def test_raw_channel_service_boundaries_at_zero_intensity(colour_runtime, value):
    """Changing X does not raise programmed intensity from zero."""
    hass, coordinator, client, data, pixels, channel = colour_runtime
    data["status"]["outInt"][0]["fc"][1] = 0
    await coordinator.async_request_refresh()
    await hass.services.async_call(
        "number",
        "set_value",
        {
            "entity_id": channel.entity_id,
            "value": value,
        },
        blocking=True,
    )
    assert data["status"]["params"]["color"] == [100, 200, 300, 400, value]
    assert data["status"]["outInt"][0]["fc"][1] == 0
