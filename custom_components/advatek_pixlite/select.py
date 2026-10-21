"""Start an on-controller Showtime scene or playlist."""
from homeassistant.components.select import SelectEntity
from homeassistant.exceptions import HomeAssistantError
from .entity import PixLiteEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([ShowtimeSelect(entry.runtime_data, "showtime", "Showtime file")])


class ShowtimeSelect(PixLiteEntity, SelectEntity):
    _attr_icon = "mdi:movie-play"

    @property
    def options(self):
        return self.coordinator.data["files"]

    @property
    def current_option(self):
        status = self.coordinator.data["status"]
        file = (status.get("params") or {}).get("file")
        return file if status.get("mode") == "playback" and file in self.options else None

    async def async_select_option(self, option):
        if option not in self.options:
            raise HomeAssistantError("File is no longer available; refresh the file list")
        await self.coordinator.command("modePlayback", {"op": "File", "file": option, "cnt": 0})
