"""Playback controls."""
from homeassistant.components.button import ButtonEntity
from .entity import PixLiteEntity

CONTROLS = [
    ("blank", "Blackout", "modePlayback", {"op": "Blank"}),
    ("freeze", "Freeze outputs", "modePlayback", {"op": "Freeze"}),
    ("live", "Return to live input", "modeLive", None),
    ("pause", "Pause playback", "playbackCtrl", {"op": "Paus"}),
    ("resume", "Resume playback", "playbackCtrl", {"op": "Play"}),
    ("restart", "Restart current mode", "modeCtrl", {"op": "Rst"}),
    ("next", "Next playlist item", "playbackCtrl", {"op": "Nxt"}),
    ("previous", "Previous playlist item", "playbackCtrl", {"op": "Prv"}),
    ("refresh", "Refresh Showtime files", None, None),
]


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([PixLiteButton(entry.runtime_data, *control) for control in CONTROLS])


class PixLiteButton(PixLiteEntity, ButtonEntity):
    def __init__(self, coordinator, key, name, command, params):
        super().__init__(coordinator, key, name)
        self.command_name, self.params = command, params

    async def async_press(self):
        if self.command_name is None:
            self.coordinator.files_updated = 0
            await self.coordinator.async_request_refresh()
        else:
            await self.coordinator.command(self.command_name, self.params)
