"""Real HA fixtures; replace only controller transport, never HA modules."""
from copy import deepcopy

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.advatek_pixlite.api import InvalidAuth, PixLiteClient, PixLiteError
from custom_components.advatek_pixlite.const import DOMAIN


def device(mac="AC-DE-48-00-00-80"):
    return {
        "version": {"apiVer": [{"maj": "v1", "min": [0, 9]}], "nickname": "Garden"},
        "constant": {"dev": {"prodFamilyName": "PixLite Mk3", "prodName": "PixLite A4-S Mk3",
                                "macAddr": mac, "auxPorts": 1, "pixPorts": 1,
                                "pwrBanksIn": 1, "pwrOut": True, "pwrPixVolts": True},
                     "ver": {"fw": "test", "hw": "test"}},
        "status": {"mode": "playback", "params": {"op": "File", "file": "show.pl"},
                   "state": {"item": 1, "op": "File", "file": "scene.scn", "paus": False},
                   "outInt": [{"out": "Pix", "progPri": "Hi", "fc": [255, 128]},
                              {"out": "Aux:1", "progPri": "Hi", "fc": [255, 128]}]},
        "statistic": {"dev": {"cpu": 12, "temp": {"current": 31.5}, "bankVolt": [12000]},
                      "pixData": {"outFrmRate": 40, "inFrmRate": 40, "liveIntAv": False},
                      "pixPwrOuts": {"current": [1500], "voltage": [11900], "stat": ["Good"]},
                      "auxData": {"liveIntAv": [False]}},
        "config": {"pix": {"colorType": "RGB"}, "operIf": {"pal": [[255, 0, 0]], "colorRes": "8Bit"},
                   "auxPort": {"mode": ["DMX512Out"]}},
        "files": [{"file": "show.pl"}, {"file": "scene.scn"}],
        "commands": [], "offline": False, "auth_failed": False,
    }


@pytest.fixture(autouse=True)
def enable_custom(enable_custom_integrations):
    """Allow this repository's integration in the real HA loader."""


@pytest.fixture
def controllers(monkeypatch):
    devices = {"controller.local": device()}

    async def exchange(client, method, path, body=None):
        from urllib.parse import urlparse
        current = devices[urlparse(client.base_url).hostname]
        if current["offline"]:
            raise PixLiteError("Unavailable")
        if current["auth_failed"]:
            raise InvalidAuth("Rejected")
        if method == "GET":
            return deepcopy(current["version"])
        name = body["req"]
        if name.endswith("Read"):
            key = name[:-4]
            if current.get("fail_read") == key:
                raise PixLiteError("Read failed")
            return {key: deepcopy(current[key])}
        if name == "fileList":
            return {"files": deepcopy(current["files"])}
        current["commands"].append(deepcopy(body))
        return {}

    monkeypatch.setattr(PixLiteClient, "_exchange", exchange)
    return devices


@pytest.fixture
def entry(hass):
    result = MockConfigEntry(domain=DOMAIN, title="Garden", unique_id="acde48000080",
                            data={"host": "controller.local", "username": "admin", "password": "", "use_ssl": False})
    result.add_to_hass(hass)
    return result
