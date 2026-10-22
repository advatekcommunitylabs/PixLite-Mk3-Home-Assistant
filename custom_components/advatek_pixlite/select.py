"""Start an on-controller Showtime scene or playlist."""

from homeassistant.components.select import SelectEntity
from homeassistant.exceptions import HomeAssistantError

from .controls import color_params, palette, pixel_intensity, solid_color
from .entity import PixLiteEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(
        [
            ShowtimeSelect(entry.runtime_data, "showtime", "Showtime file"),
            PlaylistSelect(entry.runtime_data, "playlist", "Showtime playlist"),
            PaletteSelect(entry.runtime_data, "palette", "Showtime colour preset"),
            IntensityPrioritySelect(
                entry.runtime_data, "intensity_priority", "Intensity priority"
            ),
        ]
    )


class ShowtimeSelect(PixLiteEntity, SelectEntity):
    _attr_icon = "mdi:movie-play"

    @property
    def options(self):
        return self.coordinator.data["files"]

    @property
    def current_option(self):
        status = self.coordinator.data["status"]
        file = (status.get("params") or {}).get("file")
        return (
            file if status.get("mode") == "playback" and file in self.options else None
        )

    async def async_select_option(self, option):
        if option not in self.options:
            raise HomeAssistantError(
                "File is no longer available; refresh the file list"
            )
        await self.coordinator.command(
            "modePlayback", {"op": "File", "file": option, "cnt": 0}
        )


class PlaylistSelect(ShowtimeSelect):
    _attr_icon = "mdi:playlist-play"

    @property
    def options(self):
        return [file for file in super().options if file.lower().endswith(".pl")]


class PaletteSelect(PixLiteEntity, SelectEntity):
    _attr_icon = "mdi:palette"

    @property
    def options(self):
        return [f"Preset {i + 1}" for i in range(len(palette(self.coordinator.data)))]

    @property
    def current_option(self):
        current = solid_color(self.coordinator.data)
        for i, color in enumerate(palette(self.coordinator.data)):
            if current is not None and (current + (0,) * (5 - len(current))) == (
                color + (0,) * (5 - len(color))
            ):
                return self.options[i]
        return None

    @property
    def extra_state_attributes(self):
        return {
            "colours_16bit": dict(zip(self.options, palette(self.coordinator.data)))
        }

    async def async_select_option(self, option):
        if option not in self.options:
            raise HomeAssistantError("Colour preset is no longer available")
        color = palette(self.coordinator.data)[self.options.index(option)]
        fade = self.coordinator.data["config"].get("operIf", {}).get("fadeMs", 0)
        await self.coordinator.command("modePlayback", color_params(color, fade))


class IntensityPrioritySelect(PixLiteEntity, SelectEntity):
    _attr_options = ["Override live intensity", "Yield to live intensity"]

    @property
    def current_option(self):
        priority = pixel_intensity(self.coordinator.data).get("progPri")
        return {"Hi": self._attr_options[0], "Lo": self._attr_options[1]}.get(priority)

    async def async_select_option(self, option):
        if option not in self._attr_options:
            raise HomeAssistantError("Unknown intensity priority")
        await self.coordinator.command(
            "progInt",
            {
                "item": [
                    {
                        "out": "Pix",
                        "op": "Hi" if option == self._attr_options[0] else "Lo",
                    }
                ]
            },
        )
