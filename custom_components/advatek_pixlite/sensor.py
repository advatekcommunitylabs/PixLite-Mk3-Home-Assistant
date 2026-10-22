"""System and per-output measurements."""
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.const import EntityCategory
from .entity import PixLiteEntity, value_at


async def async_setup_entry(hass, entry, async_add_entities):
    c = entry.runtime_data
    specs = [
        ("temperature", "Temperature", "statistic.dev.temp.current", "°C", SensorDeviceClass.TEMPERATURE, 1),
        ("cpu", "CPU usage", "statistic.dev.cpu", "%", None, 1),
        ("output_rate", "Output frame rate", "statistic.pixData.outFrmRate", "Hz", SensorDeviceClass.FREQUENCY, 1),
        ("input_rate", "Input frame rate", "statistic.pixData.inFrmRate", "Hz", SensorDeviceClass.FREQUENCY, 1),
        ("mode", "Mode", "status.mode", None, None, 1),
        ("file", "Playback file", "status.params.file", None, None, 1),
        ("playlist_item", "Playlist item", "status.state.item", None, None, 1),
        ("playlist_item_type", "Playlist item type", "status.state.op", None, None, 1),
        ("playlist_item_file", "Playlist item file", "status.state.file", None, None, 1),
    ]
    dev = c.client.constants["dev"]
    for i in range(dev.get("pwrBanksIn", 0)):
        specs.append((f"bank_{i+1}_voltage", f"Bank {i+1} voltage", f"statistic.dev.bankVolt.{i}", "V", SensorDeviceClass.VOLTAGE, 1000))
    if dev.get("pwrOut"):
        for i in range(dev.get("pixPorts", 0)):
            specs.append((f"output_{i+1}_current", f"Output {i+1} current", f"statistic.pixPwrOuts.current.{i}", "A", SensorDeviceClass.CURRENT, 1000))
            specs.append((f"output_{i+1}_status", f"Output {i+1} power status", f"statistic.pixPwrOuts.stat.{i}", None, None, 1))
            if dev.get("pwrPixVolts"):
                specs.append((f"output_{i+1}_voltage", f"Output {i+1} voltage", f"statistic.pixPwrOuts.voltage.{i}", "V", SensorDeviceClass.VOLTAGE, 1000))
    async_add_entities([PixLiteSensor(c, *spec) for spec in specs])


class PixLiteSensor(PixLiteEntity, SensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, key, name, path, unit, device_class, divisor):
        super().__init__(coordinator, key, name)
        self.path, self.divisor = path, divisor
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        if unit:
            self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self):
        value = value_at(self.coordinator.data, self.path)
        if value is None:
            return None
        return value / self.divisor if self._attr_native_unit_of_measurement else value
