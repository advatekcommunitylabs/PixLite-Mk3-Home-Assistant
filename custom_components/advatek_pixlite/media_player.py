"""Showtime playlist player and browser for files already on the controller."""
import math

from homeassistant.components.media_player import (
    BrowseMedia, MediaClass, MediaPlayerEntity, MediaPlayerEntityFeature,
    MediaPlayerState,
)
from homeassistant.components.media_player.errors import BrowseError
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN
from .controls import transition_ms
from .entity import PixLiteEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([PlaylistPlayer(entry.runtime_data)])


class PlaylistPlayer(PixLiteEntity, MediaPlayerEntity):
    _attr_icon = "mdi:playlist-play"
    _attr_supported_features = (
        MediaPlayerEntityFeature.PLAY_MEDIA | MediaPlayerEntityFeature.BROWSE_MEDIA
        | MediaPlayerEntityFeature.PLAY | MediaPlayerEntityFeature.PAUSE
        | MediaPlayerEntityFeature.NEXT_TRACK | MediaPlayerEntityFeature.PREVIOUS_TRACK
    )

    def __init__(self, coordinator):
        super().__init__(coordinator, "playlist_player", "Showtime playlist player")

    @property
    def playlists(self):
        return [file for file in self.coordinator.data["files"] if file.lower().endswith(".pl")]

    @property
    def active_playlist(self):
        status = self.coordinator.data["status"]
        params = status.get("params") or {}
        file = params.get("file", "")
        if status.get("mode") == "playback" and params.get("op") == "File" and file.lower().endswith(".pl"):
            return file
        return None

    @property
    def state(self):
        if self.active_playlist is None:
            return MediaPlayerState.IDLE
        state = self.coordinator.data["status"].get("state") or {}
        if state.get("err"):
            return MediaPlayerState.IDLE
        return MediaPlayerState.PAUSED if state.get("paus") else MediaPlayerState.PLAYING

    @property
    def media_title(self):
        return self.active_playlist

    @property
    def media_content_id(self):
        return self.active_playlist

    @property
    def media_content_type(self):
        return DOMAIN if self.active_playlist else None

    @property
    def extra_state_attributes(self):
        if not self.active_playlist:
            return {}
        status = self.coordinator.data["status"]
        state = status.get("state") or {}
        return {"playlist_item": state.get("item"), "item_type": state.get("op"),
                "item_file": state.get("file"), "item_colour_16bit": state.get("color"),
                "elapsed_seconds": state.get("timS"),
                "repeat_count": (status.get("params") or {}).get("cnt", 0),
                "playback_error_code": (state.get("err") or {}).get("code")}

    async def async_browse_media(self, media_content_type=None, media_content_id=None):
        if media_content_id not in (None, "", "playlists"):
            raise BrowseError("Unknown playlist folder")
        return BrowseMedia(
            title="Showtime playlists", media_class=MediaClass.DIRECTORY,
            media_content_id="playlists", media_content_type=DOMAIN,
            can_play=False, can_expand=True,
            children=[BrowseMedia(title=file, media_class=MediaClass.PLAYLIST,
                media_content_id=file, media_content_type=DOMAIN,
                can_play=True, can_expand=False) for file in self.playlists],
        )

    async def async_play_media(self, media_type, media_id, **kwargs):
        if media_type not in (DOMAIN, "playlist") or media_id not in self.playlists:
            raise HomeAssistantError("Choose a playlist stored on this controller")
        if kwargs.get("announce") or kwargs.get("enqueue") not in (None, "replace"):
            raise HomeAssistantError("Playlist queuing and announcements are not supported")
        extra = kwargs.get("extra") or {}
        count = extra.get("repeat_count", 0)
        fade = extra.get("transition", 0)
        if type(count) is not int or not 0 <= count <= 65535:
            raise HomeAssistantError("repeat_count must be an integer from 0 to 65535 (0 loops forever)")
        if isinstance(fade, bool) or not isinstance(fade, (int, float)) or not math.isfinite(fade) or not 0 <= fade <= 4294967.295:
            raise HomeAssistantError("transition must be a non-negative duration in seconds")
        await self.coordinator.command("modePlayback", {"op": "File", "file": media_id,
                                                        "cnt": count, "fadeMs": transition_ms(fade)})

    async def _control(self, operation):
        if not self.active_playlist:
            raise HomeAssistantError("Select a Showtime playlist first")
        await self.coordinator.command("playbackCtrl", {"op": operation})

    async def async_media_play(self):
        await self._control("Play")

    async def async_media_pause(self):
        await self._control("Paus")

    async def async_media_next_track(self):
        await self._control("Nxt")

    async def async_media_previous_track(self):
        await self._control("Prv")
