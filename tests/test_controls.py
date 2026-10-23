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
    light.ColorMode = SimpleNamespace(RGB="rgb", RGBW="rgbw", BRIGHTNESS="brightness")
    light.LightEntityFeature = SimpleNamespace(TRANSITION=32)
    for attr in ["BRIGHTNESS", "RGB_COLOR", "RGBW_COLOR", "TRANSITION"]:
        setattr(light, "ATTR_" + attr, attr.lower())
    monkeypatch.setitem(sys.modules, light.__name__, light)
    select = ModuleType("homeassistant.components.select")
    select.SelectEntity = type("SelectEntity", (), {})
    monkeypatch.setitem(sys.modules, select.__name__, select)
    number = ModuleType("homeassistant.components.number")
    number.NumberEntity = type("NumberEntity", (), {})
    number.NumberMode = SimpleNamespace(SLIDER="slider")
    monkeypatch.setitem(sys.modules, number.__name__, number)
    button = ModuleType("homeassistant.components.button")
    button.ButtonEntity = type("ButtonEntity", (), {})
    monkeypatch.setitem(sys.modules, button.__name__, button)
    core = ModuleType("homeassistant.core")
    core.callback = lambda func: func
    monkeypatch.setitem(sys.modules, core.__name__, core)
    player = ModuleType("homeassistant.components.media_player")
    player.__path__ = []
    player.MediaPlayerEntity = type("MediaPlayerEntity", (), {})
    player.BrowseMedia = SimpleNamespace
    player.MediaClass = SimpleNamespace(DIRECTORY="directory", PLAYLIST="playlist")
    player.MediaPlayerState = SimpleNamespace(IDLE="idle", PLAYING="playing", PAUSED="paused")
    player.MediaPlayerEntityFeature = SimpleNamespace(PLAY_MEDIA=1, BROWSE_MEDIA=2, PLAY=4, PAUSE=8, NEXT_TRACK=16, PREVIOUS_TRACK=32)
    monkeypatch.setitem(sys.modules, player.__name__, player)
    player_errors = ModuleType("homeassistant.components.media_player.errors")
    player_errors.BrowseError = type("BrowseError", (Exception,), {})
    monkeypatch.setitem(sys.modules, player_errors.__name__, player_errors)
    exc = ModuleType("homeassistant.exceptions")
    exc.HomeAssistantError = type("HomeAssistantError", (Exception,), {})
    exc.ConfigEntryAuthFailed = type("ConfigEntryAuthFailed", (Exception,), {})
    monkeypatch.setitem(sys.modules, exc.__name__, exc)
    entity = ModuleType("pixlite_test.entity")

    class Base:
        def __init__(self, coordinator, key, name):
            self.coordinator = coordinator
        @property
        def available(self):
            return self.coordinator.last_update_success

    entity.PixLiteEntity = Base
    def value_at(data, path):
        try:
            for part in path.split("."):
                data = data[int(part)] if isinstance(data, list) else data[part]
            return data
        except (KeyError, IndexError, TypeError, ValueError):
            return None
    entity.value_at = value_at
    monkeypatch.setitem(sys.modules, entity.__name__, entity)
    update = ModuleType("homeassistant.helpers.update_coordinator")
    update.DataUpdateCoordinator = type("DataUpdateCoordinator", (), {"__init__": lambda self, *a, **kw: None})
    update.UpdateFailed = type("UpdateFailed", (Exception,), {})
    monkeypatch.setitem(sys.modules, update.__name__, update)
    loaded = {name: importlib.import_module("pixlite_test." + name)
              for name in ["controls", "light", "select", "coordinator", "number", "button", "media_player"]}
    yield SimpleNamespace(**loaded)
    for name in list(sys.modules):
        if name.startswith("pixlite_test."):
            sys.modules.pop(name)


@pytest.fixture
def coordinator():
    coordinator = SimpleNamespace(data={
        "config": {"pix": {"colorType": "RGB"}, "operIf": {"pal": [[255, 0, 0]], "colorRes": "8Bit", "fadeMs": 500}},
        "status": {"mode": "playback", "params": {"op": "File", "file": "show.pl"},
                   "outInt": [{"out": "Pix", "progPri": "Hi", "fc": [20, 128]}]},
        "statistic": {"pixData": {"liveIntAv": True}},
    }, commands=AsyncMock(), command=AsyncMock(), last_update_success=True)
    async def color_commands(build_commands):
        try:
            commands = build_commands(coordinator.data)
        except ValueError as err:
            from homeassistant.exceptions import HomeAssistantError
            raise HomeAssistantError(str(err)) from err
        await coordinator.commands(commands)
    coordinator.color_commands = color_commands
    return coordinator


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
    coordinator.data["config"]["pix"]["colorType"] = "RGBWX" if len(color) == 5 else "RGB"
    coordinator.data["config"]["operIf"].update(pal=[color], colorRes=resolution)
    select = modules.select.PaletteSelect(coordinator, "palette", "Palette")
    assert select.options == ["Preset 1"]
    assert select.current_option is None
    await select.async_select_option("Preset 1")
    coordinator.commands.assert_awaited_once_with([("modePlayback", modules.controls.color_params(expected, 500))])
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
    client = SimpleNamespace(constants={"dev": {}}, read=AsyncMock(side_effect=[{"mode": "live"}, {}, config]),
                             files=AsyncMock(side_effect=modules.coordinator.PixLiteError("No card", 14)))
    coordinator = modules.coordinator.PixLiteCoordinator(None, SimpleNamespace(title="Test"), client)
    result = await coordinator._async_update_data()
    assert result["config"] == config
    assert result["files"] == []
    assert client.read.call_args.args == ("config", ["pix.colorType", "operIf"])


@pytest.mark.asyncio
@pytest.mark.parametrize("percent,factor", [(0, 0), (50, 128), (100, 255)])
async def test_aux_slider_targets_only_correct_output(modules, coordinator, percent, factor):
    coordinator.data["config"]["auxPort"] = {"mode": ["DMX512In", "DMX512Out"]}
    slider = modules.number.AuxIntensity(coordinator, 2)
    assert slider.available
    await slider.async_set_native_value(percent)
    coordinator.command.assert_awaited_once_with("progInt", {"item": [{"out": "Aux:2", "op": "HiSet", "fc": factor, "durMs": 0}]})


@pytest.mark.asyncio
async def test_aux_mode_change_blocks_commands_and_offline_availability(modules, coordinator):
    coordinator.data["config"]["auxPort"] = {"mode": ["DMX512Out"]}
    slider = modules.number.AuxIntensity(coordinator, 1)
    coordinator.last_update_success = False
    assert not slider.available
    coordinator.last_update_success = True
    coordinator.data["config"]["auxPort"]["mode"][0] = "DMX512In"
    assert not slider.available
    assert slider.native_value is None
    with pytest.raises(Exception, match="not configured"):
        await slider.async_set_native_value(50)
    coordinator.command.assert_not_awaited()


@pytest.mark.parametrize("priority,live,expected", [("Hi", True, 50), ("Lo", True, 100), ("Lo", False, 50)])
def test_aux_reports_effective_intensity(modules, coordinator, priority, live, expected):
    coordinator.data["config"]["auxPort"] = {"mode": ["DMX512Out"]}
    coordinator.data["statistic"]["auxData"] = {"liveIntAv": [live]}
    coordinator.data["status"]["outInt"].append({"out": "Aux:1", "progPri": priority, "fc": [255, 128]})
    assert modules.number.AuxIntensity(coordinator, 1).native_value == expected


@pytest.mark.asyncio
async def test_aux_entities_appear_when_enabled_and_not_duplicated(modules, coordinator):
    from unittest.mock import Mock
    coordinator.client = SimpleNamespace(constants={"dev": {"auxPorts": 2}})
    coordinator.async_add_listener = Mock(return_value=lambda: None)
    coordinator.data["config"]["auxPort"] = {"mode": ["Off", "DMX512Out"]}
    entry = SimpleNamespace(runtime_data=coordinator, async_on_unload=Mock())
    add = Mock()
    await modules.number.async_setup_entry(None, entry, add)
    assert [e.port for e in add.call_args.args[0]] == [2]
    listener = coordinator.async_add_listener.call_args.args[0]
    coordinator.data["config"]["auxPort"]["mode"][0] = "DMX512Out"
    listener()
    assert [e.port for e in add.call_args.args[0]] == [1]
    listener()
    assert add.call_count == 2
    entry.async_on_unload.assert_called_once()


@pytest.mark.asyncio
async def test_discrete_transport_buttons(modules, coordinator):
    controls = {c[1]: c for c in modules.button.CONTROLS}
    for name, op in [("Play", "Play"), ("Pause", "Paus"), ("Previous", "Prv"), ("Next", "Nxt")]:
        button = modules.button.PixLiteButton(coordinator, *controls[name])
        await button.async_press()
        coordinator.command.assert_awaited_with("playbackCtrl", {"op": op})
    assert controls["Play"][0] == "resume"  # Existing entity unique ID stays stable.


@pytest.mark.asyncio
async def test_poll_requests_aux_fields_on_capable_devices(modules):
    client = SimpleNamespace(constants={"dev": {"auxPorts": 1}},
                             read=AsyncMock(side_effect=[{}, {}, {}]), files=AsyncMock(return_value=[]))
    coordinator = modules.coordinator.PixLiteCoordinator(None, SimpleNamespace(title="Test"), client)
    await coordinator._async_update_data()
    calls = client.read.call_args_list
    assert "auxData" in calls[1].args[1]
    assert "auxPort.mode" in calls[2].args[1]


@pytest.mark.asyncio
async def test_playlist_selector_and_browser_filter_scenes(modules, coordinator):
    coordinator.data["files"] = ["show.pl", "Rainbow.scn", "Evening.PL"]
    select = modules.select.PlaylistSelect(coordinator, "playlist", "Playlist")
    assert select.options == ["show", "Evening"]
    assert select.current_option == "show"
    await select.async_select_option("Evening")
    coordinator.command.assert_awaited_once_with("modePlayback", {"op": "File", "file": "Evening.PL", "cnt": 0})
    player = modules.media_player.PlaylistPlayer(coordinator)
    tree = await player.async_browse_media()
    assert [child.title for child in tree.children] == select.options
    assert [child.media_content_id for child in tree.children] == ["show.pl", "Evening.PL"]
    assert all(child.can_play and not child.can_expand for child in tree.children)
    coordinator.data["files"] = []
    assert (await player.async_browse_media()).children == []


@pytest.mark.asyncio
@pytest.mark.parametrize("count", [0, 1, 3, 65535])
async def test_playlist_repeat_count_and_fade(modules, coordinator, count):
    coordinator.data["files"] = ["show.pl"]
    player = modules.media_player.PlaylistPlayer(coordinator)
    await player.async_play_media("advatek_pixlite", "show.pl", extra={"repeat_count": count, "transition": 1.5})
    coordinator.command.assert_awaited_once_with("modePlayback", {"op": "File", "file": "show.pl", "cnt": count, "fadeMs": 1500})
    assert "durMs" not in coordinator.command.call_args.args[1]


@pytest.mark.asyncio
@pytest.mark.parametrize("extra", [{"repeat_count": -1}, {"repeat_count": 65536}, {"repeat_count": True}, {"repeat_count": 1.5}, {"transition": -1}, {"transition": float("nan")}])
async def test_invalid_playlist_options_do_not_send_commands(modules, coordinator, extra):
    coordinator.data["files"] = ["show.pl"]
    with pytest.raises(Exception):
        await modules.media_player.PlaylistPlayer(coordinator).async_play_media("playlist", "show.pl", extra=extra)
    coordinator.command.assert_not_awaited()


@pytest.mark.asyncio
async def test_playlist_status_and_transport(modules, coordinator):
    player = modules.media_player.PlaylistPlayer(coordinator)
    coordinator.data["status"]["state"] = {"item": 2, "op": "File", "file": "Rainbow.scn", "paus": True, "timS": 42}
    assert player.state == "paused"
    assert player.media_title == "show"
    assert player.extra_state_attributes["item_file"] == "Rainbow"
    for method, op in [("async_media_play", "Play"), ("async_media_pause", "Paus"), ("async_media_next_track", "Nxt"), ("async_media_previous_track", "Prv")]:
        await getattr(player, method)()
        coordinator.command.assert_awaited_with("playbackCtrl", {"op": op})
    coordinator.data["status"]["state"] = {"item": 3, "op": "Color", "color": [65535, 0, 0]}
    assert player.state == "playing"
    assert player.extra_state_attributes["item_file"] is None
    coordinator.data["status"] = {"mode": "live"}
    assert player.state == "idle"
    assert player.media_title is None
    assert player.extra_state_attributes == {}
    with pytest.raises(Exception, match="Select a Showtime playlist"):
        await player.async_media_next_track()


@pytest.mark.asyncio
async def test_playlist_rejects_unknown_files_and_queueing(modules, coordinator):
    coordinator.data["files"] = ["show.pl", "scene.scn"]
    player = modules.media_player.PlaylistPlayer(coordinator)
    for file in ["missing.pl", "scene.scn", "https://example.com/show.pl"]:
        with pytest.raises(Exception, match="stored on this controller"):
            await player.async_play_media("playlist", file)
    with pytest.raises(Exception, match="not supported"):
        await player.async_play_media("playlist", "show.pl", enqueue="add")
    coordinator.command.assert_not_awaited()


@pytest.mark.parametrize("kind,expected", [("RGB", "rgb"), ("RGBW", "rgbw"), ("RGBWX", "rgbw")])
def test_colour_mode_follows_controller_selection(modules, coordinator, kind, expected):
    coordinator.data["config"]["pix"]["colorType"] = kind
    light = modules.light.PixLiteLight(coordinator)
    assert light.supported_color_modes == {expected}
    assert light.color_mode == expected


@pytest.mark.asyncio
async def test_rgbw_picker_retains_four_channels(modules, coordinator):
    coordinator.data["config"]["pix"]["colorType"] = "RGBW"
    light = modules.light.PixLiteLight(coordinator)
    await light.async_turn_on(rgbw_color=(1, 2, 3, 255))
    assert coordinator.commands.call_args.args[0][0][1]["color"] == [257, 514, 771, 65535]


@pytest.mark.asyncio
async def test_rgbwx_from_file_starts_with_zero_x(modules, coordinator):
    coordinator.data["config"]["pix"]["colorType"] = "RGBWX"
    light = modules.light.PixLiteLight(coordinator)
    await light.async_turn_on(rgbw_color=(1, 2, 3, 4))
    assert coordinator.commands.call_args.args[0][0][1]["color"] == [257, 514, 771, 1028, 0]


@pytest.mark.parametrize("kind", [None, "", "Unknown", ["RGB"]])
@pytest.mark.asyncio
async def test_unknown_colour_type_rejects_picker_palette_and_blank_restore(modules, coordinator, kind):
    coordinator.data["config"]["pix"]["colorType"] = kind
    light = modules.light.PixLiteLight(coordinator)
    assert light.supported_color_modes == {"brightness"}
    with pytest.raises(Exception, match="missing or unsupported"):
        await light.async_turn_on(rgb_color=(1, 2, 3))
    with pytest.raises(Exception, match="missing or unsupported"):
        await modules.select.PaletteSelect(coordinator, "palette", "Palette").async_select_option("Preset 1")
    coordinator.data["status"]["params"] = {"op": "Blank"}
    with pytest.raises(Exception, match="missing or unsupported"):
        await light.async_turn_on()
    coordinator.commands.assert_not_awaited()
    await light.async_turn_on(brightness=90)
    assert coordinator.commands.call_args.args[0] == [("progInt", modules.controls.intensity_params(90))]


@pytest.mark.parametrize("kind,count", [("RGB", 3), ("RGBW", 4), ("RGBWX", 5)])
@pytest.mark.asyncio
async def test_blank_restore_sends_configured_channel_count(modules, coordinator, kind, count):
    coordinator.data["config"]["pix"]["colorType"] = kind
    coordinator.data["status"]["params"] = {"op": "Blank"}
    await modules.light.PixLiteLight(coordinator).async_turn_on()
    assert coordinator.commands.call_args.args[0][0][1]["color"] == [65535, 65535, 65535] + [0] * (count - 3)


@pytest.mark.parametrize("kind,channel,resolution,color,expected", [
    ("RGBW", 3, "8Bit", [1, 2, 3, 4], [257, 514, 771, 12345]),
    ("RGBWX", 3, "16Bit", [1, 2, 3, 4, 5], [1, 2, 3, 12345, 5]),
    ("RGBWX", 4, "16Bit", [1, 2, 3, 4, 5], [1, 2, 3, 4, 12345]),
    ("RGBWX", 4, "8Bit", [1, 2, 3, 4, 5], [257, 514, 771, 1028, 12345]),
])
@pytest.mark.asyncio
async def test_raw_channel_preserves_other_channels_and_intensity(modules, coordinator, kind, channel, resolution, color, expected):
    coordinator.data["config"]["pix"]["colorType"] = kind
    coordinator.data["status"]["params"] = {"op": "Color", "color": color, "colorRes": resolution}
    entity = modules.number.SolidColorChannel(coordinator, channel)
    assert entity.available
    assert entity.native_value == color[channel] * (257 if resolution == "8Bit" else 1)
    await entity.async_set_native_value(12345)
    assert coordinator.commands.call_args.args[0] == [("modePlayback", modules.controls.color_params(expected))]
    coordinator.command.assert_not_awaited()


@pytest.mark.parametrize("value", [-1, 65536, 1.5, True, float("nan"), float("inf"), "3"])
@pytest.mark.asyncio
async def test_raw_channel_rejects_invalid_values(modules, coordinator, value):
    with pytest.raises(Exception, match="integer between"):
        await modules.number.SolidColorChannel(coordinator, 4).async_set_native_value(value)
    coordinator.commands.assert_not_awaited()


@pytest.mark.asyncio
async def test_raw_channel_never_replaces_file_or_reuses_removed_channel(modules, coordinator):
    coordinator.data["config"]["pix"]["colorType"] = "RGBWX"
    entity = modules.number.SolidColorChannel(coordinator, 4)
    assert not entity.available
    assert entity.native_value is None
    with pytest.raises(Exception, match="solid colour"):
        await entity.async_set_native_value(100)
    coordinator.data["config"]["pix"]["colorType"] = "RGBW"
    with pytest.raises(Exception, match="not supported"):
        await entity.async_set_native_value(100)
    coordinator.commands.assert_not_awaited()


@pytest.mark.parametrize("resolution,color", [("8Bit", [1, 2, 3, 4, 256]), ("16Bit", [1, 2, 3, 4]), ("16Bit", [1, 2, 3, 4, True]), ("Bogus", [1, 2, 3, 4, 5])])
@pytest.mark.asyncio
async def test_malformed_x_is_not_overwritten_by_picker(modules, coordinator, resolution, color):
    coordinator.data["config"]["pix"]["colorType"] = "RGBWX"
    coordinator.data["status"]["params"] = {"op": "Color", "color": color, "colorRes": resolution}
    with pytest.raises(Exception, match="cannot be preserved"):
        await modules.light.PixLiteLight(coordinator).async_turn_on(rgbw_color=(1, 2, 3, 4))
    coordinator.commands.assert_not_awaited()


@pytest.mark.asyncio
async def test_palette_channel_mismatch_is_rejected(modules, coordinator):
    coordinator.data["config"]["pix"]["colorType"] = "RGBWX"
    with pytest.raises(Exception, match="configured pixel channels"):
        await modules.select.PaletteSelect(coordinator, "palette", "Palette").async_select_option("Preset 1")
    coordinator.commands.assert_not_awaited()


@pytest.mark.asyncio
async def test_colour_commands_read_current_configuration_before_any_write(modules):
    client = SimpleNamespace(constants={"dev": {}},
        read=AsyncMock(side_effect=[{"pix": {"colorType": "Unsupported"}}, {}]), request=AsyncMock())
    coordinator = modules.coordinator.PixLiteCoordinator(None, SimpleNamespace(title="Test"), client)
    coordinator.data = {"config": {"pix": {"colorType": "RGBWX"}}}
    coordinator.async_request_refresh = AsyncMock()
    def build(data):
        modules.controls.require_color_channels(data)
        return [("modePlayback", {})]
    with pytest.raises(Exception, match="missing or unsupported"):
        await coordinator.color_commands(build)
    client.request.assert_not_awaited()
    coordinator.async_request_refresh.assert_awaited_once()


@pytest.mark.asyncio
async def test_concurrent_raw_channel_changes_use_latest_status(modules):
    from copy import deepcopy
    data = {"config": {"pix": {"colorType": "RGBWX"}}, "status": {"mode": "playback", "params": {
        "op": "Color", "color": [1, 2, 3, 4, 5], "colorRes": "16Bit"}}}
    async def read(name, paths=None):
        await asyncio.sleep(0)
        return deepcopy(data[name])
    async def request(name, params):
        await asyncio.sleep(0)
        data["status"]["params"] = deepcopy(params)
    client = SimpleNamespace(read=AsyncMock(side_effect=read), request=AsyncMock(side_effect=request))
    coordinator = modules.coordinator.PixLiteCoordinator(None, SimpleNamespace(title="Test"), client)
    coordinator.data = deepcopy(data)
    coordinator.async_request_refresh = AsyncMock()
    await asyncio.gather(
        modules.number.SolidColorChannel(coordinator, 3).async_set_native_value(12345),
        modules.number.SolidColorChannel(coordinator, 4).async_set_native_value(54321))
    assert data["status"]["params"]["color"] == [1, 2, 3, 12345, 54321]


@pytest.mark.asyncio
async def test_raw_channels_appear_only_once_as_configuration_changes(modules, coordinator):
    from unittest.mock import Mock
    coordinator.client = SimpleNamespace(constants={"dev": {"auxPorts": 0}})
    coordinator.async_add_listener = Mock(return_value=lambda: None)
    entry = SimpleNamespace(runtime_data=coordinator, async_on_unload=Mock())
    add = Mock()
    await modules.number.async_setup_entry(None, entry, add)
    add.assert_not_called()
    listener = coordinator.async_add_listener.call_args.args[0]
    coordinator.data["config"]["pix"]["colorType"] = "RGBW"
    listener()
    assert [entity.channel for entity in add.call_args.args[0]] == [3]
    coordinator.data["config"]["pix"]["colorType"] = "RGBWX"
    listener()
    assert [entity.channel for entity in add.call_args.args[0]] == [4]
    listener()
    assert add.call_count == 2
    assert not add.call_args.args[0][0]._attr_entity_registry_enabled_default


@pytest.mark.parametrize("resolution,color", [("8Bit", [256, 0, 0]), ("16Bit", [True, 0, 0]), ("Bogus", [1, 2, 3])])
@pytest.mark.asyncio
async def test_malformed_palette_never_sends_a_colour(modules, coordinator, resolution, color):
    coordinator.data["config"]["operIf"].update(colorRes=resolution, pal=[color])
    entity = modules.select.PaletteSelect(coordinator, "palette", "Palette")
    assert entity.options == []
    with pytest.raises(Exception, match="no longer available"):
        await entity.async_select_option("Preset 1")
    coordinator.commands.assert_not_awaited()


@pytest.mark.parametrize("config", [None, {}, {"pix": None}, {"pix": []}])
@pytest.mark.asyncio
async def test_missing_configuration_blocks_colour_writes(modules, coordinator, config):
    coordinator.data["config"] = config
    entity = modules.light.PixLiteLight(coordinator)
    assert entity.color_mode == "brightness"
    with pytest.raises(Exception, match="missing or unsupported"):
        await entity.async_turn_on(rgb_color=(1, 2, 3))
    coordinator.commands.assert_not_awaited()


@pytest.mark.parametrize("failure_index", [0, 1])
@pytest.mark.asyncio
async def test_colour_write_failure_refreshes_without_retry(modules, failure_index):
    client = SimpleNamespace(read=AsyncMock(side_effect=[{"pix": {"colorType": "RGB"}}, {}]),
        request=AsyncMock(side_effect=([{}] * failure_index + [modules.coordinator.PixLiteError("rejected")])) )
    coordinator = modules.coordinator.PixLiteCoordinator(None, SimpleNamespace(title="Test"), client)
    coordinator.data = {}
    coordinator.async_request_refresh = AsyncMock()
    with pytest.raises(Exception, match="rejected"):
        await coordinator.color_commands(lambda data: [("modePlayback", {}), ("progInt", {})])
    assert client.request.await_count == failure_index + 1
    coordinator.async_request_refresh.assert_awaited_once()
