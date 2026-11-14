"""ADAR device selection and authenticated identity confirmation."""

from ipaddress import IPv4Address

import probatio
from homeassistant.config_entries import SOURCE_IGNORE, ConfigFlowResult
from homeassistant.helpers import selector

from ._adar import Device, normalize_mac
from .api import PixLiteError
from .discovery import get_discovery


class AdarFlow:
    """Add discovery steps to the controller's configuration flow."""

    _selected: Device | None = None

    async def async_step_discover(self, user_input=None) -> ConfigFlowResult:
        """Search the enabled interfaces and offer a bounded device selection."""
        result = await get_discovery(self.hass).async_scan()
        self._discovered = {device.mac: device for device in result.devices}
        self._scan_complete = result.complete
        if not self._discovered:
            if result.complete:
                return await self.async_step_no_devices()
            return await self.async_step_scan_failed()
        return await self.async_step_select_device()

    async def async_step_no_devices(self, user_input=None) -> ConfigFlowResult:
        """Offer retry or manual setup after an empty scan."""
        return self.async_show_menu(
            step_id="no_devices", menu_options=["discover", "manual"]
        )

    async def async_step_scan_failed(self, user_input=None) -> ConfigFlowResult:
        """Offer retry or manual setup when the scan could not finish."""
        return self.async_show_menu(
            step_id="scan_failed", menu_options=["discover", "manual"]
        )

    async def async_step_select_device(self, user_input=None) -> ConfigFlowResult:
        """Require selection from the result of the current scan."""
        if user_input is not None:
            device = self._discovered.get(user_input.get("device"))
            if device is None:
                return self.async_abort(reason="device_not_found")
            return await self._async_discovered(device)
        return self.async_show_form(
            step_id="select_device",
            data_schema=probatio.Schema(
                {
                    probatio.Required("device"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                {
                                    "value": mac,
                                    "label": f"{device.nickname or device.model} ({device.host}, {mac})",
                                }
                                for mac, device in self._discovered.items()
                            ],
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            ),
            errors={} if self._scan_complete else {"base": "scan_incomplete"},
        )

    async def async_step_integration_discovery(
        self, discovery_info
    ) -> ConfigFlowResult:
        """Handle a device offered by the running ADAR discovery manager."""
        try:
            mac = normalize_mac(discovery_info["mac"])
            if not isinstance(discovery_info["host"], str):
                raise ValueError
            host = IPv4Address(discovery_info["host"])
            if host.is_unspecified or host.is_multicast or int(host) == 0xFFFFFFFF:
                raise ValueError
            model = discovery_info["model"]
            nickname = discovery_info.get("nickname", "")
            if not isinstance(model, str) or not model or not isinstance(nickname, str):
                raise ValueError
            device = Device(
                mac,
                str(host),
                model,
                nickname,
                False,
                True,
                True,
            )
        except (KeyError, TypeError, ValueError):
            return self.async_abort(reason="invalid_discovery")
        return await self._async_discovered(device)

    async def _async_discovered(self, device: Device) -> ConfigFlowResult:
        """Authenticate an existing entry before changing its saved address."""
        self._selected = device
        await self.async_set_unique_id(device.mac)
        existing = next(
            (
                entry
                for entry in self._async_current_entries(include_ignore=True)
                if entry.unique_id == device.mac
            ),
            None,
        )
        if existing is not None:
            if existing.source == SOURCE_IGNORE:
                return self.async_abort(reason="already_configured")
            if existing.data["host"] == device.host:
                return self.async_abort(reason="already_configured")
            data = dict(existing.data, host=device.host)
            try:
                _, identity = await self._identify(data)
            except PixLiteError:
                return self.async_abort(reason="cannot_connect")
            if identity != device.mac:
                return self.async_abort(reason="wrong_device")
            self._abort_if_unique_id_configured(updates={"host": device.host})
        return await self.async_step_discovery_confirm()

    async def async_step_discovery_confirm(self, user_input=None) -> ConfigFlowResult:
        """Collect credentials, then confirm the ADAR MAC through the API."""
        return await self._form("discovery_confirm", user_input)
