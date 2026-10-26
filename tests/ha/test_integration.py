"""Config flows, platform registration, services and lifecycle through HA Core."""
from copy import deepcopy

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.advatek_pixlite.const import DOMAIN
from .conftest import device

pytestmark = pytest.mark.asyncio
DATA = {"host": "controller.local", "username": "admin", "password": "", "use_ssl": False}


async def setup(hass, entry):
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED


def entity_id(hass, entry, domain, key):
    return er.async_get(hass).async_get_entity_id(domain, DOMAIN, f"{entry.unique_id}_{key}")


async def test_user_flow_and_duplicate(hass, controllers):
    flow = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert flow["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(flow["flow_id"], DATA)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    flow = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(flow["flow_id"], DATA)
    assert result["reason"] == "already_configured"


@pytest.mark.parametrize("kind,error", [("offline", "cannot_connect"), ("auth_failed", "invalid_auth"),
                                       ("unsupported", "unsupported_device"), ("malformed", "cannot_connect"),
                                       ("invalid_host", "invalid_host")])
async def test_flow_errors(hass, controllers, kind, error):
    data = dict(DATA)
    if kind in ("offline", "auth_failed"):
        controllers["controller.local"][kind] = True
    elif kind == "unsupported":
        controllers["controller.local"]["version"]["apiVer"][0]["min"] = [0, 8]
    elif kind == "malformed":
        controllers["controller.local"]["version"]["apiVer"] = [None]
    else:
        data["host"] = "http://bad/path"
    flow = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(flow["flow_id"], data)
    assert error in result["errors"].values()


@pytest.mark.parametrize("source", ["reconfigure", "reauth"])
@pytest.mark.parametrize("port,tls", [(0, False), (0, True), (9090, False)])
async def test_reconfigure_port_replacement_and_reload(hass, entry, controllers, source, port, tls):
    hass.config_entries.async_update_entry(entry, data=DATA | {"port": 8080})
    await setup(hass, entry)
    flow = await hass.config_entries.flow.async_init(DOMAIN, context={"source": source, "entry_id": entry.entry_id},
                                                    data=entry.data if source == "reauth" else None)
    result = await hass.config_entries.flow.async_configure(flow["flow_id"], DATA | {"port": port, "use_ssl": tls})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == ("reauth_successful" if source == "reauth" else "reconfigure_successful")
    await hass.async_block_till_done()
    assert entry.data["port"] == (port or None)
    assert entry.runtime_data.client.base_url.endswith(f":{port or (4443 if tls else 80)}")


@pytest.mark.parametrize("source", ["reconfigure", "reauth"])
async def test_wrong_device_flow_preserves_entry(hass, entry, controllers, source):
    controllers["controller.local"]["constant"]["dev"]["macAddr"] = "AC-DE-48-00-00-81"
    before = dict(entry.data)
    flow = await hass.config_entries.flow.async_init(DOMAIN, context={"source": source, "entry_id": entry.entry_id},
                                                    data=entry.data if source == "reauth" else None)
    result = await hass.config_entries.flow.async_configure(flow["flow_id"], DATA)
    assert result["reason"] == "wrong_device"
    assert dict(entry.data) == before


@pytest.mark.parametrize("failure", ["offline", "first_refresh", "wrong_device", "malformed"])
async def test_setup_failure_and_retry(hass, entry, controllers, failure):
    current = controllers["controller.local"]
    if failure == "offline":
        current["offline"] = True
    elif failure == "first_refresh":
        current["fail_read"] = "status"
    elif failure == "wrong_device":
        current["constant"]["dev"]["macAddr"] = "AC-DE-48-00-00-81"
    else:
        current["version"]["apiVer"] = [None]
    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_RETRY
    controllers["controller.local"] = device()
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED


async def test_setup_auth_failure(hass, entry, controllers):
    controllers["controller.local"]["auth_failed"] = True
    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert any(flow["context"]["source"] == "reauth" for flow in hass.config_entries.flow.async_progress())


async def test_all_platforms_units_and_services(hass, entry, controllers):
    await setup(hass, entry)
    domains = {state.domain for state in hass.states.async_all() if state.entity_id in
               {e.entity_id for e in er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)}}
    assert domains == {"sensor", "binary_sensor", "button", "select", "light", "number", "media_player"}
    for key, expected, unit in [("temperature", "31.5", "°C"), ("bank_1_voltage", "12.0", "V"),
                                ("output_1_current", "1.5", "A"), ("output_rate", "40.0", "Hz")]:
        state = hass.states.get(entity_id(hass, entry, "sensor", key))
        assert state.state == expected
        assert state.attributes["unit_of_measurement"] == unit
    assert hass.states.get(entity_id(hass, entry, "binary_sensor", "paused")).state == "off"
    for domain, action, key, data in [
        ("button", "press", "pause", {}),
        ("light", "turn_on", "pixels", {"brightness": 80}),
        ("number", "set_value", "aux_1_intensity", {"value": 50}),
        ("select", "select_option", "playlist", {"option": "show.pl"}),
        ("media_player", "play_media", "playlist_player", {"media_content_type": DOMAIN, "media_content_id": "show.pl"}),
    ]:
        await hass.services.async_call(domain, action, {"entity_id": entity_id(hass, entry, domain, key)} | data, blocking=True)
    assert [c["req"] for c in controllers["controller.local"]["commands"]] == ["playbackCtrl", "progInt", "progInt", "modePlayback", "modePlayback"]


@pytest.mark.parametrize("outage", [True, False])
async def test_recovery_identity_and_independent_controller(hass, entry, controllers, outage):
    await setup(hass, entry)
    controllers["other.local"] = device("AC-DE-48-00-00-82")
    other = MockConfigEntry(domain=DOMAIN, title="Other", unique_id="acde48000082", data=DATA | {"host": "other.local"})
    other.add_to_hass(hass)
    await setup(hass, other)
    coordinator = entry.runtime_data
    if outage:
        controllers["controller.local"]["offline"] = True
        await coordinator.async_refresh()
        assert hass.states.get(entity_id(hass, entry, "light", "pixels")).state == "unavailable"
    controllers["controller.local"] = device("AC-DE-48-00-00-81")
    await coordinator.async_refresh()
    assert not coordinator.last_update_success
    assert hass.states.get(entity_id(hass, entry, "light", "pixels")).state == "unavailable"
    assert controllers["controller.local"]["requests"] == ["constantRead"]
    with pytest.raises(HomeAssistantError):
        await coordinator.command("modePlayback", {"op": "Blank"})
    assert controllers["controller.local"]["commands"] == []
    await hass.services.async_call("button", "press", {"entity_id": entity_id(hass, other, "button", "blank")}, blocking=True)
    assert len(controllers["other.local"]["commands"]) == 1
    controllers["controller.local"] = device()
    await coordinator.async_refresh()
    assert coordinator.last_update_success
    await hass.services.async_call("button", "press", {"entity_id": entity_id(hass, entry, "button", "blank")}, blocking=True)
    assert len(controllers["controller.local"]["commands"]) == 1


async def test_replacement_between_compound_commands_does_not_retry(hass, entry, controllers):
    await setup(hass, entry)
    original = controllers["controller.local"]
    replacement = device("AC-DE-48-00-00-81")
    original["replace_after_command"] = replacement
    coordinator = entry.runtime_data
    with pytest.raises(HomeAssistantError, match="identity mismatch"):
        await coordinator.commands([("modePlayback", {"op": "Color", "color": [65535, 0, 0]}),
                                    ("progInt", {"item": [{"out": "Pix", "op": "HiSet", "fc": 100}]})])
    await hass.async_block_till_done()
    assert [c["req"] for c in original["commands"]] == ["modePlayback"]
    assert replacement["commands"] == []
    assert set(replacement["requests"]) == {"constantRead"}
    controllers["other.local"] = device("AC-DE-48-00-00-82")
    other = MockConfigEntry(domain=DOMAIN, title="Other", unique_id="acde48000082", data=DATA | {"host": "other.local"})
    other.add_to_hass(hass)
    await setup(hass, other)
    await other.runtime_data.command("modePlayback", {"op": "Blank"})
    assert len(controllers["other.local"]["commands"]) == 1
    controllers["controller.local"] = original
    await coordinator.async_refresh()
    assert coordinator.last_update_success
    # Recovery never replays the omitted intensity write or the delivered colour.
    assert [c["req"] for c in original["commands"]] == ["modePlayback"]


@pytest.mark.parametrize("kind", ["missing_product", "invalid_product", "blank_product", "invalid_nickname"])
@pytest.mark.parametrize("path", ["flow", "setup"])
async def test_malformed_metadata_has_sanitized_ha_failure(hass, entry, controllers, kind, path, caplog):
    current = controllers["controller.local"]
    if kind == "missing_product":
        current["version"].pop("nickname")
        current["constant"]["dev"].pop("prodName")
    elif kind == "invalid_product":
        current["constant"]["dev"]["prodName"] = {"unexpected": "value"}
    elif kind == "blank_product":
        current["constant"]["dev"]["prodName"] = " "
    else:
        current["version"]["nickname"] = ["invalid"]
    data = DATA | {"password": "test-secret-password"}
    if path == "flow":
        flow = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
        result = await hass.config_entries.flow.async_configure(flow["flow_id"], data)
        assert result["errors"] == {"base": "cannot_connect"}
    else:
        hass.config_entries.async_update_entry(entry, data=data)
        assert not await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.state is ConfigEntryState.SETUP_RETRY
    assert current["commands"] == []
    assert "test-secret-password" not in caplog.text
    assert "KeyError" not in caplog.text
    assert "TypeError" not in caplog.text


async def test_dynamic_aux_and_unload_reload(hass, entry, controllers):
    controllers["controller.local"]["config"]["auxPort"]["mode"] = ["Off"]
    await setup(hass, entry)
    coordinator = entry.runtime_data
    assert entity_id(hass, entry, "number", "aux_1_intensity") is None
    controllers["controller.local"]["config"]["auxPort"]["mode"] = ["DMX512Out"]
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    aux = entity_id(hass, entry, "number", "aux_1_intensity")
    assert hass.states.get(aux).state == "50"
    controllers["controller.local"]["config"]["auxPort"]["mode"] = ["Off"]
    await coordinator.async_refresh()
    assert hass.states.get(aux).state == "unavailable"
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert not coordinator._listeners
    assert coordinator._unsub_refresh is None
    await setup(hass, entry)
    assert entry.runtime_data is not coordinator
