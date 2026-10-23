"""Exercise controller isolation with real HA platforms and two HTTP controllers."""

import asyncio
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from aiohttp import ThreadedResolver, web
import pytest
import pytest_asyncio

from homeassistant import loader
from homeassistant.auth import auth_manager_from_config
from homeassistant.config_entries import ConfigEntries
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry, entity_registry, frame
from homeassistant.setup import async_setup_component

pytestmark = pytest.mark.asyncio


class Resolver(ThreadedResolver):
    """Use the system resolver without incidental multicast discovery."""

    async def real_close(self):
        await super().close()


@pytest_asyncio.fixture
async def devices(tmp_path, unused_tcp_port):
    """Configure two controllers with the same nickname through real config flows."""
    hass = HomeAssistant(str(tmp_path))
    loader.async_setup(hass)
    frame.async_setup(hass)
    device_registry.async_setup(hass)
    await device_registry.async_load(hass)
    await entity_registry.async_load(hass)
    hass.auth = await auth_manager_from_config(hass, [{"type": "homeassistant"}], [])
    hass.config_entries = ConfigEntries(hass, {})
    await hass.config_entries.async_initialize()
    controllers = []
    runners = []
    for index, model in enumerate(("A4-S", "E16-S")):
        count = 4 if index == 0 else 16
        mac = f"e0b6f500000{index + 1}"
        data = {
            "constant": {
                "dev": {
                    "prodFamilyName": "PixLite Mk3",
                    "prodName": f"PixLite {model} Mk3",
                    "macAddr": mac,
                    "pixPorts": count,
                    "auxPorts": 1,
                    "pwrOut": index == 0,
                    "pwrPixVolts": False,
                    "pwrBanksIn": 1 if index == 0 else 0,
                },
                "ver": {"fw": "3.15.0", "hw": "1.1"},
            },
            "config": {
                "pix": {"colorType": "RGB"},
                "auxPort": {"mode": ["DMX512Out"]},
                "operIf": {"colorRes": "16Bit", "pal": [[65535, 0, 0]]},
            },
            "status": {
                "mode": "live",
                "outInt": [
                    {"out": "Pix", "progPri": "Lo", "fc": [255, 255]},
                    {"out": "Aux:1", "progPri": "Lo", "fc": [255, 255]},
                ],
            },
            "statistic": {
                "dev": {
                    "temp": {"current": 21 + 10 * index},
                    "cpu": 2,
                    "bankVolt": [24000] if index == 0 else [],
                },
                "pixData": {"liveIntAv": False, "inFrmRate": 0, "outFrmRate": 60},
                "auxData": {"liveIntAv": [False]},
                "pixPwrOuts": {"current": [0] * count, "stat": ["Good"] * count},
            },
        }
        controller = SimpleNamespace(
            data=data,
            mac=mac,
            requests=[],
            files=[f"{model}.scn", f"{model}.pl"],
            file_error=None,
            fail_read=False,
            fail_command=None,
            replace_after_write=False,
        )

        async def handler(request, controller=controller):
            if request.method == "GET":
                return web.json_response(
                    {
                        "resp": "version",
                        "result": {
                            "nickname": "Shared name",
                            "apiVer": [{"maj": "v1", "min": [0, 9]}],
                        },
                    }
                )
            assert request.query["user"] == "oper"
            body = await request.json()
            controller.requests.append(deepcopy(body))
            name, params = body["req"], body.get("params")
            if controller.fail_read and name.endswith("Read"):
                return web.Response(status=503)
            if name.endswith("Read"):
                obj = name.removesuffix("Read")
                result = {obj: controller.data[obj]}
            elif name == "fileList":
                if controller.file_error:
                    return web.json_response(
                        {"resp": name, "err": {"code": controller.file_error}}
                    )
                result = {"files": [{"file": file} for file in controller.files]}
            elif controller.fail_command == name:
                return web.json_response({"resp": name, "err": {"code": 10}})
            else:
                status = controller.data["status"]
                if name == "progInt":
                    for change in params["item"]:
                        item = next(
                            item
                            for item in status["outInt"]
                            if item["out"] == change["out"]
                        )
                        if change["op"] == "HiSet":
                            item.update(progPri="Hi")
                            item["fc"][1] = change["fc"]
                        elif change["op"] in ("Hi", "Lo"):
                            item["progPri"] = change["op"]
                elif name == "modePlayback":
                    status.update(
                        mode="playback", params=deepcopy(params), state={"paus": False}
                    )
                    if controller.replace_after_write:
                        controller.data["constant"]["dev"]["macAddr"] = "aabbccddeeff"
                elif name == "modeLive":
                    status.update(mode="live", params={}, state={})
                elif name == "playbackCtrl":
                    status.setdefault("state", {})["paus"] = params["op"] == "Paus"
                result = {}
            return web.json_response({"resp": name, "result": result})

        app = web.Application()
        app.router.add_route("*", "/{path:.*}", handler)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        controller.port = site._server.sockets[0].getsockname()[1]
        runners.append(runner)
        controllers.append(controller)

    with patch(
        "homeassistant.helpers.aiohttp_client._async_make_resolver",
        side_effect=lambda hass: Resolver(),
    ):
        try:
            assert await async_setup_component(hass, "http", {"http": {"server_host": "127.0.0.1", "server_port": unused_tcp_port}})
            for controller in controllers:
                result = await hass.config_entries.flow.async_init(
                    "advatek_pixlite",
                    context={"source": "user"},
                    data={
                        "host": "127.0.0.1",
                        "port": controller.port,
                        "username": "oper",
                        "password": "",
                        "use_ssl": False,
                    },
                )
                assert result["type"] == "create_entry", result
                controller.entry = result["result"]
            await hass.async_block_till_done()
            registry = entity_registry.async_get(hass)
            for controller in controllers:
                controller.entities = {
                    item.unique_id.removeprefix(controller.mac + "_"): item.entity_id
                    for item in entity_registry.async_entries_for_config_entry(
                        registry, controller.entry.entry_id
                    )
                }
            yield hass, controllers
        finally:
            await hass.async_stop(force=True)
            for runner in runners:
                await runner.cleanup()


async def service(hass, controller, domain, action, key, **data):
    await hass.services.async_call(
        domain, action, {"entity_id": controller.entities[key]} | data, blocking=True
    )


async def test_all_platforms_capabilities_and_duplicate_names_are_isolated(devices):
    hass, (a4, e16) = devices
    assert set(a4.entities.values()).isdisjoint(e16.entities.values())
    assert {name.split(".")[0] for name in a4.entities.values()} == {
        "sensor",
        "binary_sensor",
        "light",
        "select",
        "number",
        "button",
        "media_player",
    }
    assert "output_4_current" in a4.entities and "output_5_current" not in a4.entities
    assert not any(
        key.startswith("bank_")
        or key.startswith(tuple(f"output_{port}_" for port in range(1, 17)))
        for key in e16.entities
    )
    registry = entity_registry.async_get(hass)
    assert (
        registry.async_get(a4.entities["pixels"]).device_id
        != registry.async_get(e16.entities["pixels"]).device_id
    )
    for controller, temperature in ((a4, 21), (e16, 31)):
        assert (
            float(hass.states.get(controller.entities["temperature"]).state)
            == temperature
        )
        assert (
            controller.entry.runtime_data.control_lock
            is not (e16 if controller is a4 else a4).entry.runtime_data.control_lock
        )


async def test_repeated_commands_publish_immediate_independent_state(devices):
    hass, controllers = devices
    for values in ((51, 102), (153, 204), (17, 23)):
        await asyncio.gather(
            *(
                service(
                    hass, controller, "light", "turn_on", "pixels", brightness=value
                )
                for controller, value in zip(controllers, values, strict=True)
            )
        )
        for controller, expected in zip(controllers, values, strict=True):
            assert (
                hass.states.get(controller.entities["pixels"]).attributes["brightness"]
                == expected
            )
    first, second = controllers
    await service(hass, first, "select", "select_option", "showtime", option="A4-S")
    assert first.data["status"]["params"]["file"] == "A4-S.scn"
    assert second.data["status"]["mode"] == "live"


@pytest.mark.parametrize(
    "domain,action,key,values",
    [
        ("light", "turn_on", "pixels", {"brightness": 100}),
        ("light", "turn_on", "pixels", {"rgb_color": [10, 20, 30]}),
        ("button", "press", "blank", {}),
        ("number", "set_value", "aux_1_intensity", {"value": 50}),
        ("select", "select_option", "playlist", {"option": "A4-S"}),
        (
            "media_player",
            "play_media",
            "playlist_player",
            {"media_content_type": "advatek_pixlite", "media_content_id": "A4-S.pl"},
        ),
    ],
)
async def test_reused_address_blocks_every_output_path(
    devices, domain, action, key, values
):
    hass, (first, second) = devices
    first.data["constant"]["dev"]["macAddr"] = second.mac
    first.requests.clear()
    with pytest.raises(HomeAssistantError):
        await service(hass, first, domain, action, key, **values)
    assert not any(
        request["req"]
        in {"progInt", "modePlayback", "modeLive", "modeCtrl", "playbackCtrl"}
        for request in first.requests
    )
    await asyncio.gather(
        first.entry.runtime_data.async_refresh(),
        second.entry.runtime_data.async_refresh(),
    )
    assert hass.states.get(first.entities["temperature"]).state == "unavailable"
    assert float(hass.states.get(second.entities["temperature"]).state) == 31


async def test_failure_recovery_reload_and_unload_preserve_peer(devices):
    hass, (first, second) = devices
    first.fail_read = True
    await asyncio.gather(
        first.entry.runtime_data.async_refresh(),
        second.entry.runtime_data.async_refresh(),
    )
    assert hass.states.get(first.entities["temperature"]).state == "unavailable"
    assert float(hass.states.get(second.entities["temperature"]).state) == 31
    first.fail_read = False
    await first.entry.runtime_data.async_refresh()
    peer = second.entry.runtime_data
    assert await hass.config_entries.async_reload(first.entry.entry_id)
    await hass.async_block_till_done()
    assert peer is second.entry.runtime_data
    assert await hass.config_entries.async_unload(first.entry.entry_id)
    await peer.async_refresh()
    assert peer.last_update_success


@pytest.mark.parametrize("code", [10, 14])
async def test_handled_file_errors_observe_the_file_polling_interval(devices, code):
    hass, (first, second) = devices
    first.file_error = code
    coordinator = first.entry.runtime_data
    coordinator.files_updated = 0
    first.requests.clear()
    await coordinator.async_refresh()
    await coordinator.async_refresh()
    assert sum(request["req"] == "fileList" for request in first.requests) == 1
    assert coordinator.last_update_success


async def test_reconfigure_can_clear_custom_port(devices):
    hass, (first, second) = devices
    client = first.entry.runtime_data.client
    with (
        patch(
            "custom_components.advatek_pixlite.config_flow.PixLiteClient",
            return_value=client,
        ),
        patch.object(hass.config_entries, "async_reload", AsyncMock(return_value=True)),
    ):
        result = await hass.config_entries.flow.async_init(
            "advatek_pixlite",
            context={"source": "reconfigure", "entry_id": first.entry.entry_id},
            data={
                "host": "127.0.0.1",
                "username": "oper",
                "password": "",
                "use_ssl": False,
            },
        )
        assert result["type"] == "abort", result
        assert first.entry.data.get("port") is None
        for source in ("reconfigure", "reauth"):
            form = await hass.config_entries.flow.async_init(
                "advatek_pixlite",
                context={"source": source, "entry_id": first.entry.entry_id},
                data=None,
            )
            assert form["type"] == "form"
            assert form["data_schema"]({}).get("port") is None
            hass.config_entries.flow.async_abort(form["flow_id"])


@pytest.mark.parametrize("kind,count", [("RGB", 3), ("RGBW", 4), ("RGBWX", 5)])
@pytest.mark.parametrize("operation", ["Blank", "Color", "File", "live"])
async def test_positive_brightness_turns_on_blackout_preserving_active_modes(
    devices, kind, count, operation
):
    hass, (first, second) = devices
    first.data["config"]["pix"]["colorType"] = kind
    params = {"op": operation}
    if operation == "Color":
        params.update(color=[0] * count, colorRes="16Bit")
    elif operation == "File":
        params["file"] = "A4-S.scn"
    first.data["status"].update(
        mode="live" if operation == "live" else "playback", params=params
    )
    await first.entry.runtime_data.async_refresh()
    await service(hass, first, "light", "turn_on", "pixels", brightness=90)
    assert hass.states.get(first.entities["pixels"]).state == "on"
    assert hass.states.get(first.entities["pixels"]).attributes["brightness"] == 90
    if operation in ("File", "live"):
        assert first.data["status"]["params"] == params
    else:
        assert first.data["status"]["params"]["color"] == [65535, 65535, 65535] + [
            0
        ] * (count - 3)


async def test_identity_is_rechecked_between_writes_in_one_action(devices):
    hass, (first, second) = devices
    first.replace_after_write = True
    first.requests.clear()
    with pytest.raises(HomeAssistantError, match="different controller"):
        await service(
            hass,
            first,
            "light",
            "turn_on",
            "pixels",
            rgb_color=[10, 20, 30],
            brightness=90,
        )
    writes = [
        request["req"]
        for request in first.requests
        if not request["req"].endswith("Read")
    ]
    assert writes == ["modePlayback"]
    assert hass.states.get(first.entities["pixels"]).state == "unavailable"
    assert hass.states.get(second.entities["pixels"]).state == "on"


async def test_partial_colour_failure_is_reconciled_without_repeating_a_write(devices):
    hass, (first, second) = devices
    first.fail_command = "progInt"
    first.requests.clear()
    with pytest.raises(HomeAssistantError, match="code 10"):
        await service(
            hass,
            first,
            "light",
            "turn_on",
            "pixels",
            rgb_color=[10, 20, 30],
            brightness=90,
        )
    assert [
        request["req"]
        for request in first.requests
        if not request["req"].endswith("Read")
    ] == ["modePlayback", "progInt"]
    assert hass.states.get(first.entities["pixels"]).attributes["rgb_color"] == (
        10,
        20,
        30,
    )
    assert first.data["status"]["outInt"][0]["fc"][1] == 255
    assert second.data["status"]["mode"] == "live"


async def test_manual_file_refresh_bypasses_cooldown_and_debounce(devices):
    hass, (first, second) = devices
    for filename in ("Sunset.scn", "Aurora.scn"):
        first.files.append(filename)
        await service(hass, first, "button", "press", "refresh")
        assert (
            filename.removesuffix(".scn")
            in hass.states.get(first.entities["showtime"]).attributes["options"]
        )


@pytest.mark.parametrize("operation", ["Blank", "Color"])
async def test_zero_brightness_does_not_restore_a_visible_colour(devices, operation):
    hass, (first, second) = devices
    params = {"op": operation, "color": [0, 0, 0], "colorRes": "16Bit"}
    first.data["status"].update(mode="playback", params=params)
    await first.entry.runtime_data.async_refresh()
    first.requests.clear()
    await service(hass, first, "light", "turn_on", "pixels", brightness=0)
    assert hass.states.get(first.entities["pixels"]).state == "off"
    assert not any(request["req"] == "modePlayback" for request in first.requests)
