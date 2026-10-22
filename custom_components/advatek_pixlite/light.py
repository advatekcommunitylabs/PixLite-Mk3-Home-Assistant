"""Pixel master intensity and solid-colour playback."""

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_RGB_COLOR,
    ATTR_RGBW_COLOR,
    ATTR_TRANSITION,
    ColorMode,
    LightEntity,
    LightEntityFeature,
)

from .controls import (
    color_params,
    effective_brightness,
    intensity_params,
    solid_color,
    transition_ms,
)
from .entity import PixLiteEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([PixLiteLight(entry.runtime_data)])


class PixLiteLight(PixLiteEntity, LightEntity):
    _attr_supported_features = LightEntityFeature.TRANSITION

    def __init__(self, coordinator):
        super().__init__(coordinator, "pixels", "Pixels")
        self.last_brightness = 255

    @property
    def color_mode(self):
        kind = self.coordinator.data["config"].get("pix", {}).get("colorType", "RGB")
        # X is not necessarily a second white channel; never advertise RGBWW.
        return ColorMode.RGB if kind == "RGB" else ColorMode.RGBW

    @property
    def supported_color_modes(self):
        return {self.color_mode}

    @property
    def brightness(self):
        return effective_brightness(self.coordinator.data)

    @property
    def is_on(self):
        value = self.brightness
        if value is None:
            return None
        status = self.coordinator.data["status"]
        if (
            status.get("mode") == "playback"
            and (status.get("params") or {}).get("op") == "Blank"
        ):
            return False
        color = solid_color(self.coordinator.data)
        return value > 0 and (color is None or any(color))

    @property
    def rgb_color(self):
        color = solid_color(self.coordinator.data)
        return tuple(round(v / 257) for v in color[:3]) if color is not None else None

    @property
    def rgbw_color(self):
        color = solid_color(self.coordinator.data)
        return (
            tuple(round(v / 257) for v in (color + (0, 0, 0, 0))[:4])
            if color is not None
            else None
        )

    @property
    def extra_state_attributes(self):
        color = solid_color(self.coordinator.data)
        return {
            "x_channel_16bit": color[4] if color and len(color) == 5 else None,
            "colour_control": "Solid colour replaces current playback; brightness preserves it",
        }

    async def async_turn_on(self, **kwargs):
        duration = transition_ms(kwargs.get(ATTR_TRANSITION, 0))
        requested = kwargs.get(ATTR_RGBW_COLOR, kwargs.get(ATTR_RGB_COLOR))
        commands = []
        if requested is not None:
            color = tuple(v * 257 for v in requested)
            kind = (
                self.coordinator.data["config"].get("pix", {}).get("colorType", "RGB")
            )
            if kind == "RGBWX":
                previous = solid_color(self.coordinator.data)
                x = previous[4] if previous and len(previous) == 5 else 0
                color = (color + (0, 0, 0, 0))[:4] + (x,)
            commands.append(("modePlayback", color_params(color, duration)))
        elif ATTR_BRIGHTNESS not in kwargs:
            # A bare On after the separate Blackout button needs a visible mode.
            status = self.coordinator.data["status"]
            color = solid_color(self.coordinator.data)
            if (status.get("params") or {}).get("op") == "Blank" or (
                color is not None and not any(color)
            ):
                commands.append(
                    ("modePlayback", color_params((65535, 65535, 65535), duration))
                )
        brightness = kwargs.get(ATTR_BRIGHTNESS)
        if brightness is None:
            brightness = self.brightness or self.last_brightness
        commands.append(("progInt", intensity_params(brightness, duration)))
        await self.coordinator.commands(commands)
        if brightness:
            self.last_brightness = brightness

    async def async_turn_off(self, **kwargs):
        if self.brightness:
            self.last_brightness = self.brightness
        await self.coordinator.command(
            "progInt",
            intensity_params(0, transition_ms(kwargs.get(ATTR_TRANSITION, 0))),
        )
