"""Auxiliary DMX intensity and raw solid-colour channel controls."""

import math

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.core import callback
from homeassistant.exceptions import HomeAssistantError

from .controls import (
    color_channel_count,
    color_params,
    require_color_channels,
    solid_color,
)
from .entity import PixLiteEntity, value_at


def is_dmx_output(coordinator, port):
    return value_at(coordinator.data, f"config.auxPort.mode.{port - 1}") == "DMX512Out"


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    added = set()
    added_colors = set()

    @callback
    def add_outputs():
        entities = []
        count = color_channel_count(coordinator.data) or 0
        for channel in (3, 4):
            if channel < count and channel not in added_colors:
                added_colors.add(channel)
                entities.append(SolidColorChannel(coordinator, channel))
        for port in range(
            1, coordinator.client.constants["dev"].get("auxPorts", 0) + 1
        ):
            if port not in added and is_dmx_output(coordinator, port):
                added.add(port)
                entities.append(AuxIntensity(coordinator, port))
        if entities:
            async_add_entities(entities)

    add_outputs()
    entry.async_on_unload(coordinator.async_add_listener(add_outputs))


class SolidColorChannel(PixLiteEntity, NumberEntity):
    """Edit one raw W/X channel of an existing solid colour without changing intensity."""

    _attr_native_min_value = 0
    _attr_native_max_value = 65535
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER
    _attr_icon = "mdi:palette"
    _attr_entity_registry_enabled_default = False

    def __init__(self, coordinator, channel):
        self.channel = channel
        name = "w" if channel == 3 else "x"
        self._attr_translation_key = f"solid_color_{name}"
        super().__init__(coordinator, f"solid_color_{name}", None)

    @property
    def available(self):
        return super().available and self.native_value is not None

    @property
    def native_value(self):
        color = solid_color(self.coordinator.data)
        return (
            color[self.channel]
            if color is not None and self.channel < len(color)
            else None
        )

    async def async_set_native_value(self, value):
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or not 0 <= value <= 65535
            or int(value) != value
        ):
            raise HomeAssistantError(
                "Channel value must be an integer between 0 and 65535"
            )

        def build_color(data):
            count = require_color_channels(data)
            if self.channel >= count:
                raise ValueError(
                    "Channel is not supported by the configured pixel type"
                )
            color = solid_color(data)
            if color is None:
                raise ValueError("Select a solid colour before editing W/X channels")
            updated = list(color)
            updated[self.channel] = int(value)
            return [("modePlayback", color_params(updated))]

        await self.coordinator.color_commands(build_color)


class AuxIntensity(PixLiteEntity, NumberEntity):
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_native_unit_of_measurement = "%"
    _attr_mode = NumberMode.SLIDER
    _attr_icon = "mdi:brightness-percent"

    def __init__(self, coordinator, port):
        super().__init__(coordinator, f"aux_{port}_intensity", f"Aux {port} intensity")
        self.port = port

    @property
    def available(self):
        return super().available and is_dmx_output(self.coordinator, self.port)

    @property
    def native_value(self):
        if not is_dmx_output(self.coordinator, self.port):
            return None
        items = self.coordinator.data.get("status", {}).get("outInt", [])
        item = next(
            (item for item in items if item.get("out") == f"Aux:{self.port}"), {}
        )
        factors = item.get("fc", [])
        if len(factors) != 2:
            return None
        live = value_at(
            self.coordinator.data, f"statistic.auxData.liveIntAv.{self.port - 1}"
        )
        factor = factors[0 if item.get("progPri") != "Hi" and live else 1]
        return round(factor * 100 / 255)

    async def async_set_native_value(self, value):
        if not is_dmx_output(self.coordinator, self.port):
            raise HomeAssistantError("Auxiliary port is not configured as DMX Output")
        if not math.isfinite(value) or not 0 <= value <= 100:
            raise HomeAssistantError("Intensity must be between 0 and 100 percent")
        await self.coordinator.command(
            "progInt",
            {
                "item": [
                    {
                        "out": f"Aux:{self.port}",
                        "op": "HiSet",
                        "fc": round(value * 255 / 100),
                        "durMs": 0,
                    }
                ]
            },
        )
