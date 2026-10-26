"""Regression coverage for the five diagnostic probes in the review.

Run explicitly with pytest. These probes use the existing HA doubles and a
loopback HTTP server. Passing means the reviewed software regressions are prevented.
They do not validate a running Home Assistant instance or physical hardware.
"""
import importlib
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock

from aiohttp import ClientSession, web
import pytest


ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "review_control_tests", ROOT / "tests/test_controls.py"
)
control_tests = importlib.util.module_from_spec(spec)
spec.loader.exec_module(control_tests)
modules = control_tests.modules


@pytest.mark.asyncio
async def test_runtime_address_swap_blocks_outputs(modules):
    api = importlib.import_module("pixlite_test.api")
    first_mac, second_mac = "AA-BB-CC-00-00-01", "AA-BB-CC-00-00-02"
    device = {"mac": first_mac, "requests": [], "outputs": [], "offline": False}

    async def handler(request):
        if device["offline"]:
            return web.Response(status=503)
        if request.method == "GET":
            return web.json_response({"resp": "version", "result": {
                "apiVer": [{"maj": "v1", "min": [0, 9]}]}})
        body = await request.json()
        name = body["req"]
        device["requests"].append((device["mac"], name))
        result = {}
        if name == "constantRead":
            result = {"constant": {"dev": {
                "prodFamilyName": "PixLite Mk3", "prodName": "PixLite Mk3", "macAddr": device["mac"]}}}
        elif name.endswith("Read"):
            result = {name[:-4]: {}}
        elif name == "fileList":
            result = {"files": []}
        else:
            device["outputs"].append((device["mac"], name))
        return web.json_response({"resp": name, "result": result})

    app = web.Application()
    app.router.add_route("*", "/{path:.*}", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    try:
        async with ClientSession() as session:
            client = api.PixLiteClient(session, "127.0.0.1", port=port)
            await client.initialize()
            expected_id = client.unique_id
            coordinator = modules.coordinator.PixLiteCoordinator(
                None, SimpleNamespace(title="First controller", unique_id=expected_id), client
            )
            coordinator.async_request_refresh = AsyncMock()
            device["offline"] = True
            with pytest.raises(modules.coordinator.UpdateFailed):
                await coordinator._async_update_data()
            # Simulate another controller accepting the same credentials at this address.
            device["offline"] = False
            device["mac"] = second_mac
            with pytest.raises(modules.coordinator.UpdateFailed, match="identity mismatch"):
                await coordinator._async_update_data()
            with pytest.raises(Exception, match="identity mismatch"):
                await coordinator.command("modePlayback", {"op": "Blank"})
            assert device["outputs"] == []
            assert client.unique_id == expected_id
            assert any(mac == second_mac and name == "constantRead"
                       for mac, name in device["requests"])
            device["mac"] = first_mac
            await coordinator._async_update_data()
            await coordinator.command("modePlayback", {"op": "Blank"})
            assert device["outputs"] == [(first_mac, "modePlayback")]
    finally:
        await runner.cleanup()


@pytest.mark.asyncio
async def test_reconfigure_omitted_port_clears_previous_override(modules, monkeypatch):
    # The helper's merge semantics were checked against HA Core 2025.1.0 and
    # 2026.10.2: data_updates merges into entry.data; data replaces entry.data.
    # This probe emulates that helper. It does not run HA's config-flow manager.
    config_entries = ModuleType("homeassistant.config_entries")

    class ConfigFlow:
        def __init_subclass__(cls, **kwargs):
            pass

    config_entries.ConfigFlow = ConfigFlow
    monkeypatch.setitem(sys.modules, config_entries.__name__, config_entries)
    client_helper = ModuleType("homeassistant.helpers.aiohttp_client")
    client_helper.async_get_clientsession = lambda hass: None
    monkeypatch.setitem(sys.modules, client_helper.__name__, client_helper)
    selectors = ModuleType("homeassistant.helpers.selector")
    monkeypatch.setitem(sys.modules, selectors.__name__, selectors)
    flow_module = importlib.import_module("pixlite_test.config_flow")
    validated_ports = []

    class Client:
        unique_id = "aabbcc000001"

        def __init__(self, session, **data):
            validated_ports.append(data.get("port") or (4443 if data["use_ssl"] else 80))

        async def initialize(self):
            pass

    monkeypatch.setattr(flow_module, "PixLiteClient", Client)
    entry = SimpleNamespace(unique_id=Client.unique_id, data={
        "host": "controller.local", "username": "admin", "password": "",
        "use_ssl": False, "port": 8080,
    })
    flow = flow_module.PixLiteConfigFlow()
    flow.hass = None
    flow._get_reconfigure_entry = lambda: entry
    flow.async_set_unique_id = AsyncMock()
    flow.async_update_reload_and_abort = lambda entry, data: data
    submitted = {key: value for key, value in entry.data.items() if key != "port"}
    saved = await flow.async_step_reconfigure(submitted)
    assert validated_ports == [80]
    assert saved["port"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("versions", [[None], [{"maj": "v1", "min": None}]])
async def test_malformed_version_stays_inside_protocol_error_boundary(modules, versions):
    api = importlib.import_module("pixlite_test.api")
    client = api.PixLiteClient(None, "controller.local")
    client._exchange = AsyncMock(return_value={"apiVer": versions})
    with pytest.raises(api.PixLiteError):
        await client.initialize()


@pytest.mark.asyncio
async def test_absent_sd_card_obeys_sixty_second_interval(modules, monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(modules.coordinator.time, "monotonic", lambda: now[0])
    client = SimpleNamespace(
        constants={"dev": {}}, read=AsyncMock(return_value={}), verify_identity=AsyncMock(),
        files=AsyncMock(side_effect=modules.coordinator.PixLiteError("No card", 14)),
    )
    coordinator = modules.coordinator.PixLiteCoordinator(None, SimpleNamespace(title="Test", unique_id="aabbcc000001"), client)
    await coordinator._async_update_data()
    now[0] += 10
    await coordinator._async_update_data()
    assert client.files.await_count == 1
    assert coordinator.files_updated == 1000
    now[0] = 1060
    await coordinator._async_update_data()
    assert client.files.await_count == 2
    coordinator.files_updated = 0  # Explicit Refresh Showtime files override.
    now[0] = 1061
    await coordinator._async_update_data()
    assert client.files.await_count == 3
