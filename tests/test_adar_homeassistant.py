"""Exercise discovery through real Home Assistant flows and entry lifecycle."""

import asyncio
import json
import struct
from copy import deepcopy
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from aiohttp import ThreadedResolver
from homeassistant import loader
from homeassistant.auth import auth_manager_from_config
from homeassistant.config_entries import (
    SOURCE_IGNORE,
    SOURCE_INTEGRATION_DISCOVERY,
    ConfigEntries,
    ConfigEntryState,
)
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import device_registry, entity_registry, frame
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.advatek_pixlite import async_setup_entry, async_unload_entry
from custom_components.advatek_pixlite._adar import (
    Device,
    DiscoveryResult,
    parse_response,
)
from custom_components.advatek_pixlite.api import (
    InvalidAuth,
    PixLiteError,
    UnsupportedDevice,
)
from custom_components.advatek_pixlite.config_flow import PixLiteConfigFlow
from custom_components.advatek_pixlite.discovery import get_discovery

pytestmark = pytest.mark.asyncio

MAC = "e0b6f5e04980"
HOST = "192.0.2.10"
DATA = {"host": HOST, "username": "oper", "password": "", "use_ssl": False}
DEVICE = Device(MAC, HOST, "PixLite A4-S Mk3", "Garden", False, True, True)


class _Resolver(ThreadedResolver):
    """Avoid mDNS while retaining Home Assistant's shared-resolver cleanup."""

    async def real_close(self):
        await super().close()


@pytest_asyncio.fixture
async def ha(tmp_path):
    """Use actual HA configuration managers and all integration entity platforms."""
    hass = HomeAssistant(str(tmp_path))
    loader.async_setup(hass)
    frame.async_setup(hass)
    device_registry.async_setup(hass)
    await device_registry.async_load(hass)
    await entity_registry.async_load(hass)
    hass.auth = await auth_manager_from_config(hass, [{"type": "homeassistant"}], [])
    hass.config_entries = ConfigEntries(hass, {})
    await hass.config_entries.async_initialize()
    client = MagicMock()
    client.unique_id = MAC
    client.version = {"nickname": "Garden"}
    client.base_url = "http://192.0.2.10:80"
    client.constants = {
        "dev": {
            "prodFamilyName": "PixLite Mk3",
            "prodName": "PixLite A4-S Mk3",
            "macAddr": "E0-B6-F5-E0-49-80",
            "pixPorts": 2,
            "auxPorts": 1,
            "pwrBanksIn": 1,
            "pwrOut": True,
            "pwrPixVolts": True,
        },
        "ver": {"fw": "3.15.0", "hw": "1"},
    }
    objects = {
        "config": {
            "pix": {"colorType": "RGB"},
            "operIf": {"pal": [[255, 0, 0]], "colorRes": "8Bit"},
            "auxPort": {"mode": ["DMX512Out"]},
        },
        "status": {
            "mode": "live",
            "outInt": [
                {"out": "Pix", "progPri": "Hi", "fc": [0, 128]},
                {"out": "Aux:1", "progPri": "Hi", "fc": [0, 128]},
            ],
        },
        "statistic": {
            "dev": {"temp": {"current": 32.5}, "cpu": 7, "bankVolt": [24100]},
            "pixData": {"outFrmRate": 60, "inFrmRate": 40, "liveIntAv": False},
            "pixPwrOuts": {
                "current": [1250, 0],
                "voltage": [24000, 0],
                "stat": ["Good", "Inactv"],
            },
            "auxData": {"liveIntAv": [False]},
        },
    }

    async def read(name, paths=None):
        return deepcopy(objects[name])

    client.initialize = AsyncMock()
    client.read = AsyncMock(side_effect=read)
    client.files = AsyncMock(return_value=["show.pl"])
    client.request = AsyncMock(return_value={})
    factory = MagicMock(return_value=client)
    with (
        patch(
            "homeassistant.helpers.aiohttp_client._async_make_resolver",
            side_effect=lambda hass: _Resolver(),
        ),
        patch("custom_components.advatek_pixlite.PixLiteClient", factory),
        patch("custom_components.advatek_pixlite.config_flow.PixLiteClient", factory),
        patch(
            "custom_components.advatek_pixlite.discovery.network.async_get_adapters",
            AsyncMock(
                return_value=[{"enabled": True, "ipv4": [{"address": "192.0.2.1"}]}]
            ),
        ),
        patch(
            "custom_components.advatek_pixlite.discovery.discover",
            AsyncMock(return_value=DiscoveryResult()),
        ) as scan,
    ):
        yield hass, client, factory, scan
        for entry in hass.config_entries.async_entries("advatek_pixlite"):
            if entry.state is ConfigEntryState.LOADED:
                assert await hass.config_entries.async_unload(entry.entry_id)
        await get_discovery(hass)._async_shutdown()
    await hass.async_stop(force=True)


async def test_manual_entry_setup_unload_reload(ha):
    """Forward every platform, keep polling real, and cancel discovery on unload."""
    hass, client, factory, scan = ha
    entry = MockConfigEntry(
        domain="advatek_pixlite", title="Garden", unique_id=MAC, data=DATA
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get("light.garden_pixels") is not None
    assert any(state.domain == "media_player" for state in hass.states.async_all())
    coordinator = entry.runtime_data
    manager = get_discovery(hass)
    assert manager._task is not None
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert manager._task is None
    assert not coordinator._listeners
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    client.request.assert_not_awaited()


@pytest.mark.parametrize("selected", ["e0b6f5000001", "e0b6f5000002"])
async def test_captured_controllers_can_be_selected_without_api_access(ha, selected):
    """Offer both captured models and defer API access until credentials are submitted."""
    hass, client, factory, scan = ha
    devices = []
    for model in ("a4_s", "e16_s"):
        path = Path(__file__).parent / "fixtures" / f"adar_{model}_mk3_v3_15_0.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        packet = (
            struct.pack("!8sHH", b"DiscProt", 0x2102, 0x0101)
            + json.dumps(data).encode()
        )
        device = parse_response(packet, data["ipAddr"])
        assert device is not None
        devices.append(device)
    scan.return_value = DiscoveryResult(tuple(devices))
    result = await hass.config_entries.flow.async_init(
        "advatek_pixlite", context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "discover"}
    )
    options = next(iter(result["data_schema"].schema.values())).config["options"]
    assert {option["value"] for option in options} == {device.mac for device in devices}
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"device": selected}
    )
    assert result["step_id"] == "discovery_confirm"
    assert result["description_placeholders"]["host"] == next(
        device.host for device in devices if device.mac == selected
    )
    assert not hass.config_entries.async_entries("advatek_pixlite")
    factory.assert_not_called()


async def test_scan_select_authenticate_and_create_entry(ha):
    """Create an entry only after its API identity matches the selected ADAR MAC."""
    hass, client, factory, scan = ha
    scan.return_value = DiscoveryResult((DEVICE,))
    result = await hass.config_entries.flow.async_init(
        "advatek_pixlite", context={"source": "user"}
    )
    assert result["type"] == "menu"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "discover"}
    )
    assert result["step_id"] == "select_device"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"device": MAC}
    )
    assert result["step_id"] == "discovery_confirm"
    client.initialize.assert_not_awaited()
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {key: value for key, value in DATA.items() if key != "host"}
    )
    assert result["type"] == "create_entry"
    assert result["result"].unique_id == MAC
    assert result["data"]["host"] == HOST
    await hass.async_block_till_done()
    assert result["result"].state is ConfigEntryState.LOADED
    client.request.assert_not_awaited()


@pytest.mark.parametrize(
    "error,expected",
    [
        (InvalidAuth("bad password"), "invalid_auth"),
        (UnsupportedDevice("unsupported"), "unsupported_device"),
        (PixLiteError("offline"), "cannot_connect"),
        (TypeError("malformed version"), "cannot_connect"),
    ],
)
async def test_discovery_credentials_can_recover(ha, error, expected):
    """Keep a failed confirmation open and successfully finish after correction."""
    hass, client, factory, scan = ha
    result = await hass.config_entries.flow.async_init(
        "advatek_pixlite",
        context={"source": SOURCE_INTEGRATION_DISCOVERY},
        data={"mac": MAC, "host": HOST, "model": DEVICE.model},
    )
    client.initialize.side_effect = error
    credentials = {key: value for key, value in DATA.items() if key != "host"}
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], credentials
    )
    assert result["errors"] == {"base": expected}
    assert not hass.config_entries.async_entries("advatek_pixlite")
    client.initialize.side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], credentials
    )
    assert result["type"] == "create_entry"
    await hass.async_block_till_done()
    client.request.assert_not_awaited()


async def test_discovery_mac_mismatch_cannot_create_entry(ha):
    hass, client, factory, scan = ha
    client.unique_id = "e0b6f5e04981"
    result = await hass.config_entries.flow.async_init(
        "advatek_pixlite",
        context={"source": SOURCE_INTEGRATION_DISCOVERY},
        data={"mac": MAC, "host": HOST, "model": DEVICE.model},
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {key: value for key, value in DATA.items() if key != "host"}
    )
    assert result["errors"] == {"base": "identity_mismatch"}
    assert not hass.config_entries.async_entries("advatek_pixlite")
    client.request.assert_not_awaited()


@pytest.mark.parametrize(
    "complete,step", [(True, "no_devices"), (False, "scan_failed")]
)
async def test_no_devices_keeps_manual_setup_available(ha, complete, step):
    hass, client, factory, scan = ha
    scan.return_value = DiscoveryResult(complete=complete)
    result = await hass.config_entries.flow.async_init(
        "advatek_pixlite", context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "discover"}
    )
    assert result["step_id"] == step
    assert "manual" in result["menu_options"]
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "manual"}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], DATA)
    assert result["type"] == "create_entry"
    await hass.async_block_till_done()


async def test_partial_scan_is_labelled(ha):
    hass, client, factory, scan = ha
    scan.return_value = DiscoveryResult((DEVICE,), complete=False)
    result = await hass.config_entries.flow.async_init(
        "advatek_pixlite", context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "discover"}
    )
    assert result["errors"] == {"base": "scan_incomplete"}


@pytest.mark.parametrize("source", ["user", SOURCE_IGNORE])
async def test_existing_or_ignored_controller_does_not_duplicate(ha, source):
    hass, client, factory, scan = ha
    entry = MockConfigEntry(
        domain="advatek_pixlite",
        title="Garden",
        unique_id=MAC,
        data=DATA,
        source=source,
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        "advatek_pixlite",
        context={"source": SOURCE_INTEGRATION_DISCOVERY},
        data={"mac": MAC, "host": HOST, "model": DEVICE.model},
    )
    assert result["type"] == "abort"
    assert result["reason"] in ("already_configured", "already_ignored")
    client.initialize.assert_not_awaited()


@pytest.mark.parametrize(
    "identity,error,changed",
    [
        (MAC, None, True),
        ("e0b6f5e04981", None, False),
        (MAC, InvalidAuth("changed credentials"), False),
    ],
)
async def test_new_address_is_saved_only_after_authenticated_mac_match(
    ha, identity, error, changed
):
    hass, client, factory, scan = ha
    entry = MockConfigEntry(
        domain="advatek_pixlite",
        title="Garden",
        unique_id=MAC,
        data=DATA | {"host": "192.0.2.9", "port": 8080},
    )
    entry.add_to_hass(hass)
    client.unique_id = identity
    client.initialize.side_effect = error
    result = await hass.config_entries.flow.async_init(
        "advatek_pixlite",
        context={"source": SOURCE_INTEGRATION_DISCOVERY},
        data={"mac": MAC, "host": HOST, "model": DEVICE.model},
    )
    assert result["type"] == "abort"
    assert entry.data["host"] == (HOST if changed else "192.0.2.9")
    assert entry.data["port"] == 8080
    assert factory.call_args.kwargs["port"] == 8080
    client.request.assert_not_awaited()


@pytest.mark.parametrize(
    "data",
    [
        {},
        {"mac": None},
        {"mac": MAC, "host": "239.1.2.3", "model": "x"},
        {"mac": MAC, "host": 1, "model": "x"},
        {"mac": MAC, "host": HOST, "model": None},
        {"mac": MAC, "host": HOST, "model": "x", "nickname": []},
        {"mac": "bad", "host": HOST, "model": "x"},
    ],
)
async def test_malformed_discovery_cannot_start_setup(ha, data):
    hass, client, factory, scan = ha
    result = await hass.config_entries.flow.async_init(
        "advatek_pixlite", context={"source": SOURCE_INTEGRATION_DISCOVERY}, data=data
    )
    assert result["type"] == "abort"
    assert result["reason"] == "invalid_discovery"
    client.initialize.assert_not_awaited()


async def test_only_enabled_ipv4_interfaces_are_scanned(ha):
    hass, client, factory, scan = ha
    with patch(
        "custom_components.advatek_pixlite.discovery.network.async_get_adapters",
        AsyncMock(
            return_value=[
                {"enabled": False, "ipv4": [{"address": "192.0.2.99"}]},
                {
                    "enabled": True,
                    "ipv4": [{"address": "192.0.2.1"}, {"address": "127.0.0.1"}],
                },
                {"enabled": True, "ipv4": []},
            ]
        ),
    ):
        await get_discovery(hass).async_scan()
    scan.assert_awaited_once_with(("192.0.2.1",))


@pytest.mark.parametrize("step", ["reconfigure", "reauth"])
async def test_existing_entry_credentials_flow_reloads_without_duplicates(ha, step):
    hass, client, factory, scan = ha
    entry = MockConfigEntry(
        domain="advatek_pixlite", title="Garden", unique_id=MAC, data=DATA
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        "advatek_pixlite", context={"source": step, "entry_id": entry.entry_id}
    )
    assert result["type"] == "form"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], DATA | {"password": "new"}
    )
    assert result["type"] == "abort"
    assert entry.data["password"] == "new"
    await hass.async_block_till_done()
    assert len(hass.config_entries.async_entries("advatek_pixlite")) == 1
    client.request.assert_not_awaited()


async def test_invalid_manual_host_can_be_corrected(ha):
    hass, client, factory, scan = ha
    result = await hass.config_entries.flow.async_init(
        "advatek_pixlite", context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "manual"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], DATA | {"host": "http://invalid/"}
    )
    assert result["errors"] == {"host": "invalid_host"}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], DATA)
    assert result["type"] == "create_entry"
    await hass.async_block_till_done()


async def test_new_discovery_step_without_selection_is_rejected(ha):
    hass, client, factory, scan = ha
    result = await hass.config_entries.flow.async_init(
        "advatek_pixlite", context={"source": "discovery_confirm"}
    )
    assert result["type"] == "abort"
    assert result["reason"] == "invalid_discovery"


async def test_background_manager_shared_and_cancelled_with_last_entry(ha):
    hass, client, factory, scan = ha
    manager = get_discovery(hass)
    manager.async_start("first")
    task = manager._task
    manager.async_start("second")
    assert manager._task is task
    await manager.async_stop("first")
    assert manager._task is task
    await manager.async_stop("second")
    assert manager._task is None
    assert task.done()
    assert manager._unsub_stop is None


async def test_stale_selection_is_rejected(ha):
    hass, client, factory, scan = ha
    flow = PixLiteConfigFlow()
    flow.hass = hass
    flow._discovered = {}
    result = await flow.async_step_select_device({"device": MAC})
    assert result["reason"] == "device_not_found"
    client.initialize.assert_not_awaited()


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (InvalidAuth("denied"), ConfigEntryAuthFailed),
        (PixLiteError("offline"), ConfigEntryNotReady),
    ],
)
async def test_setup_failure_does_not_start_discovery(ha, error, expected):
    hass, client, factory, scan = ha
    client.initialize.side_effect = error
    entry = MockConfigEntry(
        domain="advatek_pixlite", title="Garden", unique_id=MAC, data=DATA
    )
    entry.add_to_hass(hass)
    with pytest.raises(expected):
        await async_setup_entry(hass, entry)
    assert get_discovery(hass)._task is None
    scan.assert_not_awaited()


async def test_failed_platform_unload_keeps_discovery_alive(ha):
    hass, client, factory, scan = ha
    entry = MockConfigEntry(
        domain="advatek_pixlite", title="Garden", unique_id=MAC, data=DATA
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    task = get_discovery(hass)._task
    with patch.object(
        hass.config_entries, "async_unload_platforms", AsyncMock(return_value=False)
    ):
        assert not await async_unload_entry(hass, entry)
    assert get_discovery(hass)._task is task
    assert not task.done()


async def test_background_scan_dispatches_flow_and_cancels_on_shutdown(ha):
    hass, client, factory, scan = ha
    scan.return_value = DiscoveryResult((DEVICE,))
    manager = get_discovery(hass)
    with patch(
        "custom_components.advatek_pixlite.discovery.discovery_flow.async_create_flow"
    ) as create:
        manager.async_start("first")
        task = manager._task
        await asyncio.sleep(0)
        create.assert_called_once_with(
            hass,
            "advatek_pixlite",
            context={"source": SOURCE_INTEGRATION_DISCOVERY},
            data={
                "mac": MAC,
                "host": HOST,
                "model": DEVICE.model,
                "nickname": DEVICE.nickname,
            },
        )
        hass.bus.async_fire(EVENT_HOMEASSISTANT_STOP)
        await hass.async_block_till_done()
        assert task.done()
        assert manager._task is None
        assert manager._unsub_stop is None
    client.initialize.assert_not_awaited()
