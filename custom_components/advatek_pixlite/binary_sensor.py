"""Playback and controller error state."""
from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorDeviceClass
from .entity import PixLiteEntity, value_at


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([
        PixLiteBinarySensor(entry.runtime_data, "playback_error", "Playback error", "status.state.err", BinarySensorDeviceClass.PROBLEM),
        PixLiteBinarySensor(entry.runtime_data, "paused", "Playback paused", "status.state.paus", None),
    ])


class PixLiteBinarySensor(PixLiteEntity, BinarySensorEntity):
    def __init__(self, coordinator, key, name, path, device_class):
        super().__init__(coordinator, key, name)
        self.path = path
        self._attr_device_class = device_class

    @property
    def is_on(self):
        return bool(value_at(self.coordinator.data, self.path))
