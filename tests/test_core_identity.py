"""Verify that the staged monitoring coordinator rejects changed or malformed identity."""

import importlib
from pathlib import Path
import sys
from types import ModuleType
from unittest.mock import Mock

import pytest
from test_device_runtime import devices as devices

from homeassistant.helpers.update_coordinator import UpdateFailed
from script.prepare_core import prepare


@pytest.mark.asyncio
@pytest.mark.parametrize("mac", [None, "aabbccddeeff", "000000000000"])
async def test_core_coordinator_uses_the_validated_identity_boundary(
    devices, monkeypatch, mac
):
    hass, (first, second) = devices
    package = ModuleType("pixlite_core_audit")
    package.__path__ = [str(Path(__file__).parents[1] / "core/advatek_pixlite")]
    monkeypatch.setitem(sys.modules, package.__name__, package)
    module = importlib.import_module(package.__name__ + ".coordinator")
    coordinator = module.PixLiteCoordinator(hass, first.entry)
    try:
        await coordinator._async_setup()
        first.data["constant"]["dev"]["macAddr"] = mac
        with pytest.raises(UpdateFailed):
            await coordinator._async_update_data()
        first.data["constant"]["dev"]["macAddr"] = first.mac
        assert (await coordinator._async_update_data())["statistic"]["dev"]["temp"][
            "current"
        ] == 21
        assert second.entry.runtime_data.last_update_success
    finally:
        await coordinator.async_shutdown()


@pytest.mark.asyncio
async def test_exported_sensor_platform_imports_and_builds_supported_entities(
    devices, tmp_path, monkeypatch
):
    hass, (first, second) = devices
    output = tmp_path / "core-export"
    prepare(output, "0.1.0", draft=True)
    package = ModuleType("pixlite_export_audit")
    package.__path__ = [str(output / "homeassistant/components/advatek_pixlite")]
    monkeypatch.setitem(sys.modules, package.__name__, package)
    module = importlib.import_module(package.__name__ + ".sensor")
    add_entities = Mock()
    await module.async_setup_entry(hass, first.entry, add_entities)
    sensors = {
        entity.entity_description.key: entity
        for entity in add_entities.call_args.args[0]
    }
    assert sensors["temperature"].native_value == 21
    assert "output_4_current" in sensors
    first.entry.runtime_data.data["status"]["params"] = {"file": "Sunset.scn"}
    assert sensors["file"].native_value == "Sunset"
