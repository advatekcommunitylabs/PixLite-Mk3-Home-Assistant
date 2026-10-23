"""Verify independent controller instances through real Home Assistant services."""

import asyncio
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from homeassistant.config_entries import SOURCE_INTEGRATION_DISCOVERY
from homeassistant.helpers import device_registry, entity_registry
from pytest_homeassistant_custom_component.common import MockConfigEntry
from test_adar_homeassistant import DATA, DEVICE, HOST, MAC
from test_adar_homeassistant import ha as ha

from custom_components.advatek_pixlite._adar import DiscoveryResult
from custom_components.advatek_pixlite.api import PixLiteError
from custom_components.advatek_pixlite.discovery import get_discovery

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def pair(ha):
    """Load two independently simulated controllers with colliding friendly names."""
    hass, template, factory, scan = ha
    original = {
        name: await template.read(name) for name in ("config", "status", "statistic")
    }
    controllers = []
    for index, model in enumerate(("A4-S", "E16-S")):
        data = DATA | {"host": f"192.0.2.{10 + index}"}
        mac = f"e0b6f500000{index + 1}"
        client = MagicMock()
        client.unique_id = mac
        client.version = {"nickname": "Shared name"}
        client.base_url = f"http://{data['host']}:80"
        client.constants = deepcopy(template.constants)
        client.constants["dev"].update(
            macAddr=mac,
            prodName=f"PixLite {model} Mk3",
            pixPorts=4 if index == 0 else 16,
            pwrOut=index == 0,
            pwrBanksIn=1 if index == 0 else 0,
            pwrPixVolts=False,
        )
        objects = deepcopy(original)
        if index == 0:
            objects["statistic"]["pixPwrOuts"].update(
                current=[1250, 0, 0, 0], stat=["Good"] * 4, voltage=None
            )
        else:
            objects["statistic"].pop("pixPwrOuts")
            objects["statistic"]["dev"]["bankVolt"] = []
        filename = f"{model}.pl"
        objects["status"].update(
            mode="playback",
            params={"op": "File", "file": filename},
            state={"item": 1, "op": "File", "file": filename},
        )
        objects["statistic"]["dev"]["temp"]["current"] = 21 + index * 10
        objects["config"]["operIf"]["pal"] = [
            [255, 0, 0] if index == 0 else [0, 0, 255]
        ]

        async def read(name, paths=None, *, objects=objects):
            return deepcopy(objects[name])

        client.read = AsyncMock(side_effect=read)
        client.initialize = AsyncMock()
        client.files = AsyncMock(return_value=[filename])
        client.request = AsyncMock(return_value={})
        entry = MockConfigEntry(
            domain="advatek_pixlite", title="Shared name", unique_id=mac, data=data
        )
        entry.add_to_hass(hass)
        controllers.append(
            SimpleNamespace(
                entry=entry, client=client, objects=objects, filename=filename
            )
        )
    by_host = {item.entry.data["host"]: item.client for item in controllers}
    factory.side_effect = lambda session, *, host, **kwargs: by_host[host]
    assert all(
        await asyncio.gather(
            *(
                hass.config_entries.async_setup(item.entry.entry_id)
                for item in controllers
            )
        )
    )
    await hass.async_block_till_done()
    registry = entity_registry.async_get(hass)
    for item in controllers:
        item.entities = {
            entry.unique_id.removeprefix(f"{item.entry.unique_id}_"): entry.entity_id
            for entry in entity_registry.async_entries_for_config_entry(
                registry, item.entry.entry_id
            )
        }
    return hass, controllers, scan


async def test_two_entries_keep_registries_and_polling_independent(pair):
    hass, (first, second), scan = pair
    assert first.entry.runtime_data is not second.entry.runtime_data
    assert (
        first.entry.runtime_data.control_lock
        is not second.entry.runtime_data.control_lock
    )
    assert first.client is not second.client
    assert set(first.entities.values()).isdisjoint(second.entities.values())
    assert "output_4_current" in first.entities
    assert "output_5_current" not in first.entities
    assert not any(
        f"output_{port}_{metric}" in second.entities
        for port in range(1, 17)
        for metric in ("current", "status", "voltage")
    )
    assert "bank_1_voltage" not in second.entities
    assert {entity.split(".")[0] for entity in first.entities.values()} == {
        "light",
        "select",
        "number",
        "button",
        "sensor",
        "binary_sensor",
        "media_player",
    }
    registry = entity_registry.async_get(hass)
    first_device = registry.async_get(first.entities["pixels"]).device_id
    second_device = registry.async_get(second.entities["pixels"]).device_id
    assert first_device != second_device
    devices = device_registry.async_get(hass)
    assert devices.async_get(first_device).identifiers == {
        ("advatek_pixlite", first.entry.unique_id)
    }
    assert devices.async_get(second_device).identifiers == {
        ("advatek_pixlite", second.entry.unique_id)
    }
    assert float(hass.states.get(first.entities["temperature"]).state) == 21
    assert float(hass.states.get(second.entities["temperature"]).state) == 31
    assert get_discovery(hass)._entries == {
        item.entry.entry_id for item in (first, second)
    }
    first.client.request.assert_not_awaited()
    second.client.request.assert_not_awaited()


async def test_one_controller_failure_and_recovery_does_not_affect_other(pair):
    hass, (first, second), scan = pair
    read = first.client.read.side_effect
    first.client.read.side_effect = PixLiteError("offline")
    await asyncio.gather(
        first.entry.runtime_data.async_refresh(),
        second.entry.runtime_data.async_refresh(),
    )
    await hass.async_block_till_done()
    assert hass.states.get(first.entities["temperature"]).state == "unavailable"
    assert float(hass.states.get(second.entities["temperature"]).state) == 31
    assert second.entry.runtime_data.last_update_success
    first.client.read.side_effect = read
    first.objects["statistic"]["dev"]["temp"]["current"] = 22
    await first.entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert float(hass.states.get(first.entities["temperature"]).state) == 22
    assert float(hass.states.get(second.entities["temperature"]).state) == 31


@pytest.mark.parametrize("target", [0, 1])
async def test_reload_and_unload_preserve_other_entry_and_shared_scanner(pair, target):
    hass, controllers, scan = pair
    first, second = controllers[target], controllers[1 - target]
    manager = get_discovery(hass)
    task = manager._task
    coordinator = second.entry.runtime_data
    registry = entity_registry.async_get(hass)
    ids = {
        entry.unique_id: entry.entity_id
        for entry in entity_registry.async_entries_for_config_entry(
            registry, first.entry.entry_id
        )
    }
    assert await hass.config_entries.async_reload(first.entry.entry_id)
    await hass.async_block_till_done()
    assert second.entry.runtime_data is coordinator
    assert manager._task is task and not task.done()
    assert ids == {
        entry.unique_id: entry.entity_id
        for entry in entity_registry.async_entries_for_config_entry(
            registry, first.entry.entry_id
        )
    }
    assert await hass.config_entries.async_unload(first.entry.entry_id)
    assert manager._task is task and not task.done()
    await second.entry.runtime_data.async_refresh()
    assert second.entry.runtime_data.last_update_success
    assert await hass.config_entries.async_unload(second.entry.entry_id)
    assert manager._task is None
    assert task.done()


@pytest.mark.parametrize(
    ("domain", "service", "key", "values", "command", "parameter"),
    [
        (
            "light",
            "turn_on",
            "pixels",
            ({"brightness": 50}, {"brightness": 200}),
            "progInt",
            "intensity",
        ),
        ("light", "turn_off", "pixels", ({}, {}), "progInt", "off"),
        (
            "select",
            "select_option",
            "showtime",
            ({"option": "A4-S.pl"}, {"option": "E16-S.pl"}),
            "modePlayback",
            "file",
        ),
        (
            "select",
            "select_option",
            "playlist",
            ({"option": "A4-S.pl"}, {"option": "E16-S.pl"}),
            "modePlayback",
            "file",
        ),
        (
            "select",
            "select_option",
            "palette",
            ({"option": "Preset 1"}, {"option": "Preset 1"}),
            "modePlayback",
            "color",
        ),
        (
            "select",
            "select_option",
            "intensity_priority",
            (
                {"option": "Override live intensity"},
                {"option": "Yield to live intensity"},
            ),
            "progInt",
            "priority",
        ),
        (
            "number",
            "set_value",
            "aux_1_intensity",
            ({"value": 25}, {"value": 75}),
            "progInt",
            "aux",
        ),
        (
            "media_player",
            "play_media",
            "playlist_player",
            (
                {
                    "media_content_type": "advatek_pixlite",
                    "media_content_id": "A4-S.pl",
                },
                {
                    "media_content_type": "advatek_pixlite",
                    "media_content_id": "E16-S.pl",
                },
            ),
            "modePlayback",
            "file",
        ),
        (
            "media_player",
            "media_play",
            "playlist_player",
            ({}, {}),
            "playbackCtrl",
            "Play",
        ),
        (
            "media_player",
            "media_pause",
            "playlist_player",
            ({}, {}),
            "playbackCtrl",
            "Paus",
        ),
        (
            "media_player",
            "media_next_track",
            "playlist_player",
            ({}, {}),
            "playbackCtrl",
            "Nxt",
        ),
        (
            "media_player",
            "media_previous_track",
            "playlist_player",
            ({}, {}),
            "playbackCtrl",
            "Prv",
        ),
    ],
)
async def test_concurrent_services_target_only_their_controller(
    pair, domain, service, key, values, command, parameter
):
    hass, controllers, scan = pair
    await asyncio.gather(
        *(
            hass.services.async_call(
                domain, service, {"entity_id": item.entities[key]} | data, blocking=True
            )
            for item, data in zip(controllers, values, strict=True)
        )
    )
    for index, item in enumerate(controllers):
        item.client.request.assert_awaited_once()
        name, params = item.client.request.call_args.args
        assert name == command
        if parameter == "file":
            assert params["file"] == item.filename
        elif parameter == "color":
            assert params["color"] == ([65535, 0, 0] if index == 0 else [0, 0, 65535])
        elif parameter in ("intensity", "off", "aux", "priority"):
            value = params["item"][0]
            assert value["out"] == ("Aux:1" if parameter == "aux" else "Pix")
            if parameter == "priority":
                assert value["op"] == ("Hi" if index == 0 else "Lo")
            else:
                assert (
                    value["fc"]
                    == {"intensity": (50, 200), "off": (0, 0), "aux": (64, 191)}[
                        parameter
                    ][index]
                )
        else:
            assert params["op"] == parameter


@pytest.mark.parametrize(
    ("first_key", "second_key", "first_call", "second_call"),
    [
        (
            "blank",
            "freeze",
            ("modePlayback", {"op": "Blank"}),
            ("modePlayback", {"op": "Freeze"}),
        ),
        ("live", "pause", ("modeLive", None), ("playbackCtrl", {"op": "Paus"})),
        (
            "resume",
            "restart",
            ("playbackCtrl", {"op": "Play"}),
            ("modeCtrl", {"op": "Rst"}),
        ),
        (
            "next",
            "previous",
            ("playbackCtrl", {"op": "Nxt"}),
            ("playbackCtrl", {"op": "Prv"}),
        ),
    ],
)
@pytest.mark.parametrize("reverse", [False, True])
async def test_playback_buttons_remain_isolated(
    pair, first_key, second_key, first_call, second_call, reverse
):
    hass, controllers, scan = pair
    first, second = reversed(controllers) if reverse else controllers
    await asyncio.gather(
        hass.services.async_call(
            "button", "press", {"entity_id": first.entities[first_key]}, blocking=True
        ),
        hass.services.async_call(
            "button", "press", {"entity_id": second.entities[second_key]}, blocking=True
        ),
    )
    first.client.request.assert_awaited_once_with(*first_call)
    second.client.request.assert_awaited_once_with(*second_call)


async def test_refreshing_file_lists_does_not_mix_instances(pair):
    hass, controllers, scan = pair
    for item in controllers:
        item.client.files.reset_mock()
    await asyncio.gather(
        *(
            hass.services.async_call(
                "button",
                "press",
                {"entity_id": item.entities["refresh"]},
                blocking=True,
            )
            for item in controllers
        )
    )
    for item in controllers:
        item.client.files.assert_awaited_once()
        assert item.entry.runtime_data.files == [item.filename]
        item.client.request.assert_not_awaited()


async def test_blocked_command_on_one_instance_does_not_block_other(pair):
    hass, (first, second), scan = pair
    entered, release = asyncio.Event(), asyncio.Event()

    async def blocked(name, params=None):
        entered.set()
        await release.wait()
        return {}

    first.client.request.side_effect = blocked
    task = asyncio.create_task(
        hass.services.async_call(
            "light",
            "turn_on",
            {"entity_id": first.entities["pixels"], "brightness": 50},
            blocking=True,
        )
    )
    try:
        await asyncio.wait_for(entered.wait(), 2)
        await asyncio.wait_for(
            hass.services.async_call(
                "light",
                "turn_on",
                {"entity_id": second.entities["pixels"], "brightness": 200},
                blocking=True,
            ),
            2,
        )
        assert not task.done()
        second.client.request.assert_awaited_once()
    finally:
        release.set()
        await task


@pytest.mark.parametrize("target", [0, 1])
async def test_failed_command_is_isolated_to_its_entry(pair, target):
    hass, controllers, scan = pair
    failed, healthy = controllers[target], controllers[1 - target]
    failed.client.request.side_effect = PixLiteError("simulated rejection")
    results = await asyncio.gather(
        hass.services.async_call(
            "button", "press", {"entity_id": failed.entities["blank"]}, blocking=True
        ),
        hass.services.async_call(
            "button", "press", {"entity_id": healthy.entities["live"]}, blocking=True
        ),
        return_exceptions=True,
    )
    assert isinstance(results[0], Exception)
    assert str(results[0]) == "simulated rejection"
    assert results[1] is None
    failed.client.request.assert_awaited_once_with("modePlayback", {"op": "Blank"})
    healthy.client.request.assert_awaited_once_with("modeLive", None)
    assert healthy.entry.runtime_data.last_update_success


async def test_simultaneous_setup_scans_are_serialized(ha):
    hass, client, factory, scan = ha
    active = peak = 0

    async def scan_once(interfaces):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        try:
            await asyncio.sleep(0.01)
            return DiscoveryResult((DEVICE,))
        finally:
            active -= 1

    scan.side_effect = scan_once
    manager = get_discovery(hass)
    results = await asyncio.gather(*(manager.async_scan() for _ in range(3)))
    assert peak == 1
    assert scan.await_count == 3
    assert all(result.devices == (DEVICE,) for result in results)


async def test_two_discovery_flows_do_not_merge_or_cancel_each_other(ha):
    hass, client, factory, scan = ha
    data = [
        {"mac": MAC, "host": HOST, "model": "PixLite A4-S Mk3"},
        {"mac": "e0b6f5000002", "host": "192.0.2.11", "model": "PixLite E16-S Mk3"},
    ]
    first, second = await asyncio.gather(
        *(
            hass.config_entries.flow.async_init(
                "advatek_pixlite",
                context={"source": SOURCE_INTEGRATION_DISCOVERY},
                data=item,
            )
            for item in data
        )
    )
    assert first["flow_id"] != second["flow_id"]
    assert first["step_id"] == second["step_id"] == "discovery_confirm"
    for result, item in zip((first, second), data, strict=True):
        assert result["description_placeholders"]["host"] == item["host"]
        duplicate = await hass.config_entries.flow.async_init(
            "advatek_pixlite",
            context={"source": SOURCE_INTEGRATION_DISCOVERY},
            data=item,
        )
        assert duplicate["type"] == "abort"
        assert duplicate["reason"] == "already_in_progress"
    hass.config_entries.flow.async_abort(first["flow_id"])
    assert (
        hass.config_entries.flow.async_get(second["flow_id"])["step_id"]
        == "discovery_confirm"
    )
    assert not hass.config_entries.async_entries("advatek_pixlite")
    factory.assert_not_called()


async def test_play_media_followed_by_pause_uses_fresh_controller_state(pair):
    """A second command must see playback started after the refresh cooldown begins."""
    hass, (first, second), scan = pair
    second.objects["status"].update(mode="live", params={}, state={})
    await second.entry.runtime_data.async_refresh()
    await second.entry.runtime_data.async_request_refresh()

    async def request(name, params=None):
        if name == "modePlayback":
            second.objects["status"].update(
                mode="playback", params=deepcopy(params), state={"paus": False}
            )
        elif name == "playbackCtrl":
            second.objects["status"]["state"]["paus"] = params["op"] == "Paus"
        return {}

    second.client.request.side_effect = request
    await hass.services.async_call(
        "media_player",
        "play_media",
        {
            "entity_id": second.entities["playlist_player"],
            "media_content_type": "advatek_pixlite",
            "media_content_id": second.filename,
        },
        blocking=True,
    )
    await hass.services.async_call(
        "media_player",
        "media_pause",
        {"entity_id": second.entities["playlist_player"]},
        blocking=True,
    )
    assert second.entry.runtime_data.data["status"]["state"]["paus"]
    first.client.request.assert_not_awaited()


async def test_normalized_rgb_status_does_not_affect_other_palette(pair):
    """Match an E16 RGB reply with its trailing zero independently of the A4."""
    hass, (first, second), scan = pair
    second.objects["status"].update(
        mode="playback",
        params={"op": "Color", "colorRes": "16Bit", "color": [0, 0, 65535, 0]},
    )
    await asyncio.gather(
        first.entry.runtime_data.async_refresh(),
        second.entry.runtime_data.async_refresh(),
    )
    await hass.async_block_till_done()
    assert hass.states.get(second.entities["palette"]).state == "Preset 1"
    assert hass.states.get(first.entities["palette"]).state != "Preset 1"
    first.client.request.assert_not_awaited()
    second.client.request.assert_not_awaited()
