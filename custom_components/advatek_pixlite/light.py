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
    color_channel_count,
    color_params,
    effective_brightness,
    intensity_params,
    require_color_channels,
    solid_color,
    transition_ms,
    validate_color,
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
        count = color_channel_count(self.coordinator.data)
        if count is None:
            return ColorMode.BRIGHTNESS
        # X has no defined warm/cold meaning in the controller API.
        return ColorMode.RGB if count == 3 else ColorMode.RGBW

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
        brightness = kwargs.get(ATTR_BRIGHTNESS)
        if requested is not None:

            def build_color(data):
                count = require_color_channels(data)
                expected = 4 if ATTR_RGBW_COLOR in kwargs else 3
                if (
                    expected != min(count, 4)
                    or len(requested) != expected
                    or any(
                        type(value) is not int or not 0 <= value <= 255
                        for value in requested
                    )
                ):
                    raise ValueError(
                        "Picker colour does not match the configured pixel channels"
                    )
                color = tuple(value * 257 for value in requested)
                if count == 5:
                    previous = solid_color(data)
                    if (
                        previous is None
                        and (data["status"].get("params") or {}).get("op") == "Color"
                    ):
                        raise ValueError(
                            "Current solid colour is unavailable; X cannot be preserved"
                        )
                    color += (previous[4] if previous is not None else 0,)
                return [
                    (
                        "modePlayback",
                        color_params(validate_color(data, color), duration),
                    ),
                    (
                        "progInt",
                        intensity_params(
                            brightness
                            if brightness is not None
                            else effective_brightness(data) or self.last_brightness,
                            duration,
                        ),
                    ),
                ]

            await self.coordinator.color_commands(build_color)
        else:

            def restore_output(data):
                status = data["status"]
                current = solid_color(data)
                target = (
                    brightness
                    if brightness is not None
                    else effective_brightness(data) or self.last_brightness
                )
                commands = []
                if target > 0 and (
                    (status.get("params") or {}).get("op") == "Blank"
                    or (current is not None and not any(current))
                ):
                    count = require_color_channels(data)
                    color = (65535, 65535, 65535) + (0,) * (count - 3)
                    commands.append(("modePlayback", color_params(color, duration)))
                commands.append(("progInt", intensity_params(target, duration)))
                return commands

            await self.coordinator.color_commands(restore_output)
        if brightness:
            self.last_brightness = brightness
        elif brightness is None and self.brightness:
            self.last_brightness = self.brightness

    async def async_turn_off(self, **kwargs):
        if self.brightness:
            self.last_brightness = self.brightness
        await self.coordinator.command(
            "progInt",
            intensity_params(0, transition_ms(kwargs.get(ATTR_TRANSITION, 0))),
        )
