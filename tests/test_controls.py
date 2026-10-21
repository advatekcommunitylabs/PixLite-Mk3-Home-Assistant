"""Protocol and entity behaviour tests; HA interfaces are lightweight test doubles."""
import asyncio
import importlib
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock

import pytest


@pytest.fixture
def modules(monkeypatch):
    root = Path(__file__).parents[1] / "custom_components/advatek_pixlite"
    # Load integration modules without booting HA or altering the user's installation.
    package = ModuleType("pixlite_test")
    package.__path__ = [str(root)]
    monkeypatch.setitem(sys.modules, "pixlite_test", package)
    for name in ["homeassistant", "homeassistant.components", "homeassistant.helpers"]:
        module = ModuleType(name)
        module.__path__ = []
        monkeypatch.setitem(sys.modules, name, module)
    light = ModuleType("homeassistant.components.light")
    light.LightEntity = type("LightEntity", (), {})
    light.ColorMode = SimpleNamespace(RGB="rgb", RGBW="rgbw")
    light.LightEntityFeature = SimpleNamespace(TRANSITION=32)
    for attr in ["BRIGHTNESS", "RGB_COLOR", "RGBW_COLOR", "TRANSITION"]:
        setattr(light, "ATTR_" + attr, attr.lower())
    monkeypatch.setitem(sys.modules, light.__name__, light)
    select = ModuleType("homeassistant.components.select")
    select.SelectEntity = type("SelectEntity", (), {})
    monkeypatch.setitem(sys.modules, select.__name__, select)
    exc = ModuleType("homeassistant.exceptions")
    exc.HomeAssistantError = type("HomeAssistantError", (Exception,), {})
    exc.ConfigEntryAuthFailed = type("ConfigEntryAuthFailed", (Exception,), {})
    monkeypatch.setitem(sys.modules, exc.__name__, exc)
    entity = ModuleType("pixlite_test.entity")

    class Base:
        def __init__(self, coordinator, key, name):
            self.coordinator = coordinator

    entity.PixLiteEntity = Base
    monkeypatch.setitem(sys.modules, entity.__name__, entity)
    update = ModuleType("homeassistant.helpers.update_coordinator")
    update.DataUpdateCoordinator = type("DataUpdateCoordinator", (), {"__init__": lambda self, *a, **kw: None})
    update.UpdateFailed = type("UpdateFailed", (Exception,), {})
    monkeypatch.setitem(sys.modules, update.__name__, update)
    loaded = {name: importlib.import_module("pixlite_test." + name)
              for name in ["controls", "light", "select", "coordinator"]}
    yield SimpleNamespace(**loaded)
    for name in list(sys.modules):
        if name.startswith("pixlite_test."):
            sys.modules.pop(name)


@pytest.fixture
def coordinator():
    return SimpleNamespace(data={
        "config": {"pix": {"colorType": "RGB"}, "operIf": {"pal": [[255, 0, 0]], "colorRes": "8Bit", "fadeMs": 500}},
        "status": {"mode": "playback", "params": {"op": "File", "file": "show.pl"},
                   "outInt": [{"out": "Pix", "progPri": "Hi", "fc": [20, 128]}]},
        "statistic": {"pixData": {"liveIntAv": True}},
    }, commands=AsyncMock(), command=AsyncMock())


@pytest.mark.asyncio
async def test_brightness_does_not_replace_scene(modules, coordinator):
    light = modules.light.PixLiteLight(coordinator)
    await light.async_turn_on(brightness=90, transition=1.25)
    coordinator.commands.assert_awaited_once_with([
        ("progInt", {"item": [{"out": "Pix", "op": "HiSet", "fc": 90, "durMs": 1250}]})])


@pytest.mark.asyncio
async def test_off_on_restores_intensity_without_restarting_scene(modules, coordinator):
    light = modules.light.PixLiteLight(coordinator)
    await light.async_turn_off(transition=2)
    assert coordinator.command.call_args.args == ("progInt", {"item": [{"out": "Pix", "op": "HiSet", "fc": 0, "durMs": 2000}]})
    coordinator.data["status"]["outInt"][0]["fc"][1] = 0
    assert light.is_on is False
    await light.async_turn_on()
    assert coordinator.commands.call_args.args[0] == [("progInt", modules.controls.intensity_params(128))]


@pytest.mark.asyncio
async def test_picker_starts_color_and_sets_brightness(modules, coordinator):
    light = modules.light.PixLiteLight(coordinator)
    await light.async_turn_on(rgb_color=(255, 100, 0), brightness=200, transition=3)
    assert coordinator.commands.call_args.args[0] == [
        ("modePlayback", {"op": "Color", "color": [65535, 25700, 0], "colorRes": "16Bit", "fadeMs": 3000}),
        ("progInt", modules.controls.intensity_params(200, 3000))]


@pytest.mark.asyncio
async def test_rgbwx_picker_preserves_x(modules, coordinator):
    coordinator.data["config"]["pix"]["colorType"] = "RGBWX"
    coordinator.data["status"]["params"] = {"op": "Color", "color": [0, 0, 0, 0, 12345], "colorRes": "16Bit"}
    light = modules.light.PixLiteLight(coordinator)
    assert light.supported_color_modes == {"rgbw"}
    await light.async_turn_on(rgbw_color=(255, 0, 0, 50))
    assert coordinator.commands.call_args.args[0][0][1]["color"] == [65535, 0, 0, 12850, 12345]


@pytest.mark.parametrize("priority,available,expected", [("Hi", True, 128), ("Lo", True, 20), ("Lo", False, 128)])
def test_reports_controlling_intensity(modules, coordinator, priority, available, expected):
    coordinator.data["status"]["outInt"][0]["progPri"] = priority
    coordinator.data["statistic"]["pixData"]["liveIntAv"] = available
    assert modules.light.PixLiteLight(coordinator).brightness == expected


def test_unknown_brightness_and_no_invented_scene_colour(modules, coordinator):
    light = modules.light.PixLiteLight(coordinator)
    assert light.rgb_color is None
    coordinator.data["status"]["outInt"] = []
    assert light.brightness is None
    assert light.is_on is None


@pytest.mark.parametrize("resolution,color,expected", [("8Bit", [255, 128, 0], [65535, 32896, 0]), ("16Bit", [123, 456, 789, 1000, 2345], [123, 456, 789, 1000, 2345])])
@pytest.mark.asyncio
async def test_palette_preserves_resolution_and_channels(modules, coordinator, resolution, color, expected):
    coordinator.data["config"]["operIf"].update(pal=[color], colorRes=resolution)
    select = modules.select.PaletteSelect(coordinator, "palette", "Palette")
    assert select.options == ["Preset 1"]
    assert select.current_option is None
    await select.async_select_option("Preset 1")
    coordinator.command.assert_awaited_once_with("modePlayback", modules.controls.color_params(expected, 500))
    coordinator.data["status"]["params"] = {"op": "Color", "color": expected, "colorRes": "16Bit"}
    assert select.current_option == "Preset 1"


@pytest.mark.asyncio
async def test_removed_palette_and_priority_validation(modules, coordinator):
    select = modules.select.PaletteSelect(coordinator, "palette", "Palette")
    coordinator.data["config"]["operIf"]["pal"] = []
    assert select.options == []
    with pytest.raises(Exception, match="no longer available"):
        await select.async_select_option("Preset 1")
    coordinator.command.assert_not_awaited()
    priority = modules.select.IntensityPrioritySelect(coordinator, "priority", "Priority")
    await priority.async_select_option("Yield to live intensity")
    coordinator.command.assert_awaited_once_with("progInt", {"item": [{"out": "Pix", "op": "Lo"}]})


@pytest.mark.asyncio
async def test_turn_on_after_blackout_with_transition(modules, coordinator):
    coordinator.data["status"]["params"] = {"op": "Blank"}
    light = modules.light.PixLiteLight(coordinator)
    assert light.is_on is False
    await light.async_turn_on(transition=1)
    assert coordinator.commands.call_args.args[0][0] == ("modePlayback", modules.controls.color_params((65535, 65535, 65535), 1000))


@pytest.mark.asyncio
async def test_multi_command_actions_do_not_interleave(modules):
    requests = []
    async def request(name, params):
        requests.append(name)
        await asyncio.sleep(0)
    client = SimpleNamespace(request=request)
    coordinator = modules.coordinator.PixLiteCoordinator(None, SimpleNamespace(title="Test"), client)
    coordinator.async_request_refresh = AsyncMock()
    await asyncio.gather(coordinator.commands([("color", {}), ("intensity", {})]), coordinator.command("pause"))
    assert requests == ["color", "intensity", "pause"]


@pytest.mark.asyncio
async def test_partial_command_failure_refreshes_without_retry(modules):
    client = SimpleNamespace(request=AsyncMock(side_effect=[{}, modules.coordinator.PixLiteError("rejected")]))
    coordinator = modules.coordinator.PixLiteCoordinator(None, SimpleNamespace(title="Test"), client)
    coordinator.async_request_refresh = AsyncMock()
    with pytest.raises(Exception, match="rejected"):
        await coordinator.commands([("color", {}), ("intensity", {})])
    assert client.request.await_count == 2
    coordinator.async_request_refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_poll_refreshes_external_palette_and_colour_type_without_sd(modules):
    config = {"pix": {"colorType": "RGBW"}, "operIf": {"pal": [[1, 2, 3, 4]], "colorRes": "16Bit"}}
    client = SimpleNamespace(read=AsyncMock(side_effect=[{"mode": "live"}, {}, config]),
                             files=AsyncMock(side_effect=modules.coordinator.PixLiteError("No card", 14)))
    coordinator = modules.coordinator.PixLiteCoordinator(None, SimpleNamespace(title="Test"), client)
    result = await coordinator._async_update_data()
    assert result["config"] == config
    assert result["files"] == []
    assert client.read.call_args.args == ("config", ["pix.colorType", "operIf"])
