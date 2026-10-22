"""Common controller entity."""

from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN


class PixLiteEntity(CoordinatorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, key, name):
        super().__init__(coordinator)
        client = coordinator.client
        self._attr_unique_id = f"{client.unique_id}_{key}"
        if name is not None:
            self._attr_name = name
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, client.unique_id)},
            manufacturer="Advatek Lighting",
            model=client.constants["dev"].get("prodName"),
            name=client.version.get("nickname") or client.constants["dev"]["prodName"],
            sw_version=client.constants.get("ver", {}).get("fw"),
            hw_version=client.constants.get("ver", {}).get("hw"),
            configuration_url=client.base_url,
        )


def value_at(data, path):
    try:
        for part in path.split("."):
            data = data[int(part)] if isinstance(data, list) else data[part]
        return data
    except KeyError, IndexError, TypeError, ValueError:
        return None
