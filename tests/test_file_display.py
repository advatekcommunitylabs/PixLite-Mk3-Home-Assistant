"""Verify extensionless labels through Home Assistant's actual entity services."""

import logging
from datetime import timedelta

import pytest
import pytest_asyncio
from homeassistant.auth import auth_manager_from_config
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import EntityPlatform
from homeassistant.setup import async_setup_component
from test_colour_contract import colour_runtime as colour_runtime

from custom_components.advatek_pixlite.file_names import display_name
from custom_components.advatek_pixlite.media_player import PlaylistPlayer
from custom_components.advatek_pixlite.select import PlaylistSelect, ShowtimeSelect
from custom_components.advatek_pixlite.sensor import SENSORS, PixLiteSensor

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def file_runtime(colour_runtime, unused_tcp_port):
    """Publish file entities with controller responses held in memory."""
    hass, coordinator, client, data, pixels, channel = colour_runtime
    hass.auth = await auth_manager_from_config(hass, [{"type": "homeassistant"}], [])
    assert await async_setup_component(
        hass,
        "http",
        {"http": {"server_host": "127.0.0.1", "server_port": unused_tcp_port}},
    )
    data["files"] = ["Evening.scn", "Evening.pl", "multi.part.SCN", "UPPER.PL"]
    data["status"].update(
        mode="playback",
        params={"op": "File", "file": "Evening.pl"},
        state={"op": "File", "file": "Sunset.SCN"},
    )
    coordinator.async_set_updated_data(data)
    scenes = ShowtimeSelect(coordinator, "showtime", "Showtime scene")
    playlists = PlaylistSelect(coordinator, "playlist", "Showtime playlist")
    player = PlaylistPlayer(coordinator)
    sensors = [
        PixLiteSensor(coordinator, description)
        for description in SENSORS
        if description.key in ("file", "playlist_item_file")
    ]
    entities = {
        "select": [scenes, playlists],
        "media_player": [player],
        "sensor": sensors,
    }
    platforms = []
    for domain, items in entities.items():
        assert await async_setup_component(hass, domain, {})
        platform = EntityPlatform(
            hass=hass,
            logger=logging.getLogger(__name__),
            domain=domain,
            platform_name="advatek_pixlite",
            platform=None,
            scan_interval=timedelta(seconds=30),
            entity_namespace=None,
        )
        platform.config_entry = coordinator.config_entry
        platforms.append(platform)
        for index, entity in enumerate(items):
            entity.entity_id = f"{domain}.file_display_{index}"
            entity._attr_entity_registry_enabled_default = True
        await platform.async_add_entities(items)
    await hass.async_block_till_done()
    yield hass, coordinator, client, data, scenes, playlists, player, sensors
    for platform in platforms:
        await platform.async_reset()


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("Evening.pl", "Evening"),
        ("Sunset.SCN", "Sunset"),
        ("multi.part.scn", "multi.part"),
        ("show.pl.scn", "show.pl"),
        ("unchanged.txt", "unchanged.txt"),
        (None, None),
    ],
)
async def test_display_name_removes_only_the_final_known_extension(filename, expected):
    assert display_name(filename) == expected


async def test_published_labels_separate_scenes_and_playlists(file_runtime):
    hass, coordinator, client, data, scenes, playlists, player, sensors = file_runtime
    assert hass.states.get(scenes.entity_id).attributes["options"] == [
        "Evening",
        "multi.part",
    ]
    assert hass.states.get(playlists.entity_id).attributes["options"] == [
        "Evening",
        "UPPER",
    ]
    assert scenes.name == "Showtime scene"
    assert playlists.name == "Showtime playlist"
    assert scenes.current_option is None
    assert playlists.current_option == "Evening"
    assert player.media_title == "Evening"
    assert player.media_content_id == "Evening.pl"
    assert player.extra_state_attributes["item_file"] == "Sunset"
    assert [hass.states.get(sensor.entity_id).state for sensor in sensors] == [
        "Evening",
        "Sunset",
    ]


@pytest.mark.parametrize(("index", "filename"), [(4, "Evening.scn"), (5, "Evening.pl")])
async def test_identical_names_route_to_the_correct_full_filename(
    file_runtime, index, filename
):
    hass, coordinator, client, data, scenes, playlists, player, sensors = file_runtime
    entity = file_runtime[index]
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": entity.entity_id, "option": "Evening"},
        blocking=True,
    )
    client.request.assert_awaited_once_with(
        "modePlayback", {"op": "File", "file": filename, "cnt": 0}
    )


async def test_browser_titles_keep_full_playable_ids(file_runtime):
    hass, coordinator, client, data, scenes, playlists, player, sensors = file_runtime
    tree = await player.async_browse_media()
    assert [(item.title, item.media_content_id) for item in tree.children] == [
        ("Evening", "Evening.pl"),
        ("UPPER", "UPPER.PL"),
    ]
    await player.async_play_media(
        tree.children[0].media_content_type, tree.children[0].media_content_id
    )
    assert client.request.call_args.args[1]["file"] == "Evening.pl"


async def test_removed_or_ambiguous_names_do_not_send_commands(file_runtime):
    hass, coordinator, client, data, scenes, playlists, player, sensors = file_runtime
    data["files"] = ["Other.scn"]
    coordinator.async_set_updated_data(data)
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            "select",
            "select_option",
            {"entity_id": scenes.entity_id, "option": "Evening"},
            blocking=True,
        )
    data["files"] = ["Same.scn", "Same.SCN"]
    coordinator.async_set_updated_data(data)
    assert scenes.options == ["Same"]
    with pytest.raises(HomeAssistantError, match="ambiguous"):
        await scenes.async_select_option("Same")
    client.request.assert_not_awaited()
