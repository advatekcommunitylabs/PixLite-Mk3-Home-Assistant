"""Playback controls."""

from homeassistant.components.button import ButtonEntity

from .entity import PixLiteEntity

CONTROLS = [
    ("blank", "Blank", "modePlayback", {"op": "Blank"}),
    ("freeze", "Freeze", "modePlayback", {"op": "Freeze"}),
    ("live", "Live Data", "modeLive", None),
    ("pause", "Pause", "playbackCtrl", {"op": "Paus"}),
    ("resume", "Play", "playbackCtrl", {"op": "Play"}),
    ("restart", "Restart current mode", "modeCtrl", {"op": "Rst"}),
    ("next", "Next", "playbackCtrl", {"op": "Nxt"}),
    ("previous", "Previous", "playbackCtrl", {"op": "Prv"}),
    ("refresh", "Refresh Showtime files", None, None),
]


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(
        [PixLiteButton(entry.runtime_data, *control) for control in CONTROLS]
    )


class PixLiteButton(PixLiteEntity, ButtonEntity):
    def __init__(self, coordinator, key, name, command, params):
        super().__init__(coordinator, key, name)
        self.command_name, self.params = command, params
        icons = {
            "resume": "mdi:play",
            "pause": "mdi:pause",
            "previous": "mdi:skip-previous",
            "next": "mdi:skip-next",
        }
        if key in icons:
            self._attr_icon = icons[key]

    async def async_press(self):
        if self.command_name is None:
            self.coordinator.files_updated = 0
            await self.coordinator.async_refresh()
        else:
            await self.coordinator.command(self.command_name, self.params)
