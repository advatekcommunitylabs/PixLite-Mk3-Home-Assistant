"""Common controller entity."""

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import PixLiteCoordinator


class PixLiteEntity(CoordinatorEntity[PixLiteCoordinator]):
    """Group entities under a stable controller identity."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: PixLiteCoordinator, key: str, name: str | None
    ) -> None:
        """Initialize the controller identity and device metadata."""
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


def value_at(data: Any, path: str) -> Any:
    """Look up an optional value in a nested controller snapshot."""
    try:
        for part in path.split("."):
            data = data[int(part)] if isinstance(data, list) else data[part]
        return data
    except KeyError, IndexError, TypeError, ValueError:
        return None
