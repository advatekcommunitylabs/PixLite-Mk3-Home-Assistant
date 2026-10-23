"""Connect ADAR discovery to Home Assistant interfaces and config flows."""

from __future__ import annotations

import asyncio
from ipaddress import IPv4Address

from homeassistant.components import network
from homeassistant.config_entries import SOURCE_IGNORE, SOURCE_INTEGRATION_DISCOVERY
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant
from homeassistant.helpers import discovery_flow

from ._adar import DiscoveryResult, discover
from .const import DOMAIN

DISCOVERY_INTERVAL = 300


def get_discovery(hass: HomeAssistant) -> AdarDiscovery:
    """Return the single discovery manager shared by entries and setup flows."""
    data = hass.data.setdefault(DOMAIN, {})
    if "discovery" not in data:
        data["discovery"] = AdarDiscovery(hass)
    return data["discovery"]


class AdarDiscovery:
    """Run bounded scans while entries are loaded, and cancel on unload or stop."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._lock = asyncio.Lock()
        self._entries: set[str] = set()
        self._task: asyncio.Task | None = None
        self._unsub_stop = None

    async def async_scan(self) -> DiscoveryResult:
        """Scan enabled IPv4 adapters; simultaneous setup scans do not overlap."""
        async with self._lock:
            addresses = []
            for adapter in await network.async_get_adapters(self.hass):
                if not adapter["enabled"]:
                    continue
                for config in adapter["ipv4"]:
                    address = IPv4Address(config["address"])
                    if not address.is_loopback and not address.is_unspecified:
                        addresses.append(str(address))
            return await discover(tuple(addresses))

    def async_start(self, entry_id: str) -> None:
        """Start one background loop for all loaded controller entries."""
        self._entries.add(entry_id)
        if self._task is None or self._task.done():
            self._task = self.hass.async_create_background_task(
                self._run(), "PixLite ADAR discovery"
            )
            self._unsub_stop = self.hass.bus.async_listen_once(
                EVENT_HOMEASSISTANT_STOP, self._async_shutdown
            )

    async def async_stop(self, entry_id: str) -> None:
        """Release an entry and stop discovery when the final entry unloads."""
        self._entries.discard(entry_id)
        if not self._entries:
            await self._async_shutdown()

    async def _async_shutdown(self, event=None) -> None:
        """Cancel background work and remove the shutdown listener."""
        self._entries.clear()
        if self._unsub_stop is not None:
            self._unsub_stop()
            self._unsub_stop = None
        if self._task is not None:
            task, self._task = self._task, None
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def _run(self) -> None:
        """Offer discovered devices without issuing controller output commands."""
        while self._entries:
            result = await self.async_scan()
            ignored = {
                entry.unique_id
                for entry in self.hass.config_entries.async_entries(DOMAIN)
                if entry.source == SOURCE_IGNORE
            }
            for device in result.devices:
                if device.mac not in ignored:
                    discovery_flow.async_create_flow(
                        self.hass,
                        DOMAIN,
                        context={"source": SOURCE_INTEGRATION_DISCOVERY},
                        data={
                            "mac": device.mac,
                            "host": device.host,
                            "model": device.model,
                            "nickname": device.nickname,
                        },
                    )
            await asyncio.sleep(DISCOVERY_INTERVAL)
