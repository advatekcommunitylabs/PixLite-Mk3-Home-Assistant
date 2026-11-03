"""Exercise the actual HTTP client against an in-process controller simulator."""
import asyncio
import importlib.util
from pathlib import Path
import sys
from unittest.mock import AsyncMock

import aiohttp
from aiohttp import web
import pytest
import pytest_asyncio

spec = importlib.util.spec_from_file_location("pixlite_api", Path(__file__).parents[1] / "custom_components/advatek_pixlite/_client/__init__.py")
api = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = api
spec.loader.exec_module(api)


@pytest_asyncio.fixture
async def controller():
    state = {"requests": [], "active": 0, "peak": 0, "error": None, "http": 200, "minor": [0, 9]}

    async def handler(request):
        state["active"] += 1
        state["peak"] = max(state["peak"], state["active"])
        try:
            await asyncio.sleep(0.005)
            if request.method == "GET":
                assert request.path == "/ver"
                assert not request.query
                return web.json_response({"resp": "version", "result": state.get("version", {"apiVer": state.get("versions", [{"maj": "v1", "min": state["minor"]}])})})
            assert request.path == "/v1.9/"
            body = await request.json()
            assert next(iter(body)) == "req"
            assert request.query["auth"] == api.password_hash("secret")
            assert request.query["user"] == "oper"
            state["requests"].append(body)
            if state.get("invalid_json"):
                return web.Response(text="not JSON", content_type="application/json")
            if state["http"] != 200:
                return web.Response(status=state["http"])
            response = {"resp": body["req"]}
            if "error_envelope" in state:
                response["err"] = state["error_envelope"]
            elif state["error"]:
                response["err"] = {"code": state["error"], "msg": "test"}
            elif body["req"] == "constantRead":
                response["result"] = {"constant": state.get("constants", {"dev": {"prodFamilyName": "PixLite Mk3", "prodName": "PixLite Mk3", "macAddr": state.get("mac", "AC-DE-48-00-00-80")}})}
            elif body["req"] == "fileList":
                response["result"] = {"files": [{"file": "Rainbow.scn"}, {"file": "Loop.pl"}, {"file": "notes.txt"}]}
            elif body["req"] == "statusRead":
                response["result"] = {"status": {"mode": "live"}}
            return web.json_response(response)
        finally:
            state["active"] -= 1

    app = web.Application()
    app.router.add_route("*", "/{path:.*}", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    async with aiohttp.ClientSession() as session:
        yield api.PixLiteClient(session, "127.0.0.1", "oper", "secret", port=port), state
    await runner.cleanup()


def test_documented_empty_password_hash():
    assert api.password_hash("") == "47DEQpj8HBSa-_TImW-5JCeuQeRkm5NMpJWZG3hSuFU"


@pytest.mark.parametrize("host", ["http://controller", "controller/path", "controller:80", "a?auth=x", ""])
def test_reject_url_as_host(host):
    with pytest.raises(ValueError):
        api.normalize_host(host)


@pytest.mark.asyncio
async def test_initialize_and_files(controller):
    client, state = controller
    await client.initialize()
    assert client.unique_id == "acde48000080"
    assert await client.files() == ["Loop.pl", "Rainbow.scn"]
    assert state["requests"][0]["params"] == {"path": ["dev", "ver"]}


@pytest.mark.asyncio
async def test_serializes_requests(controller):
    client, state = controller
    await asyncio.gather(*(client.read("status") for _ in range(6)))
    assert state["peak"] == 1


@pytest.mark.asyncio
async def test_playback_and_empty_result(controller):
    client, state = controller
    await client.request("modePlayback", {"op": "File", "file": "Rainbow.scn", "cnt": 0})
    assert list(state["requests"][0]["params"]) == ["op", "file", "cnt"]
    assert await client.request("playbackCtrl", {"op": "Paus"}) == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("code", [10, 14, 16, 999])
async def test_api_errors_inside_http_200(controller, code):
    client, state = controller
    state["error"] = code
    with pytest.raises(api.PixLiteError) as caught:
        await client.files()
    assert caught.value.code == code
    assert "secret" not in str(caught.value)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 403, 503])
async def test_http_failures(controller, status):
    client, state = controller
    state["http"] = status
    with pytest.raises(api.InvalidAuth if status in (401, 403) else api.PixLiteError):
        await client.read("status")


@pytest.mark.asyncio
async def test_reject_older_api(controller):
    client, state = controller
    state["minor"] = [0, 8]
    with pytest.raises(api.UnsupportedDevice):
        await client.initialize()


@pytest.mark.asyncio
async def test_separate_controllers_have_separate_locks(controller):
    client, state = controller
    other = api.PixLiteClient(client.session, "example.local")
    assert client.lock is not other.lock


@pytest.mark.asyncio
@pytest.mark.parametrize("versions", [None, 1, {}, [None], ["v1"], [{"maj": "v1", "min": None}], [{"maj": "v1", "min": "09"}], [{"maj": "v1", "min": [0]}], [{"maj": "v1", "min": [0, "9"]}], [{"maj": "v1", "min": [False, 9]}], [{"maj": "v1", "min": [9, 0]}]])
async def test_malformed_versions_raise_protocol_errors(controller, versions):
    client, state = controller
    state["versions"] = versions
    with pytest.raises(api.PixLiteError, match="Invalid API version"):
        await client.initialize()


@pytest.mark.asyncio
@pytest.mark.parametrize("mac", [None, 123, [], {}, "", "invalid", "aa:bb-cc:dd:ee:ff", "aabbccddeefg", "000000000000", "ffffffffffff", "010000000001"])
async def test_malformed_macs_raise_protocol_errors(controller, mac):
    client, state = controller
    state["mac"] = mac
    with pytest.raises(api.PixLiteError, match="Invalid controller MAC"):
        await client.initialize()


@pytest.mark.asyncio
async def test_live_identity_check_does_not_replace_cached_identity(controller):
    client, state = controller
    await client.initialize()
    await client.verify_identity(client.unique_id)
    state["mac"] = "aa:bb:cc:dd:ee:ff"
    with pytest.raises(api.PixLiteError, match="different controller"):
        await client.verify_identity(client.unique_id)
    assert client.unique_id == "acde48000080"
    state["mac"] = "AC-DE-48-00-00-80"
    await client.verify_identity(client.unique_id)


@pytest.mark.asyncio
async def test_intensity_and_color_wire_format(controller):
    client, state = controller
    await client.request("progInt", {"item": [{"out": "Pix", "op": "HiSet", "fc": 100, "durMs": 1500}]})
    await client.request("modePlayback", {"op": "Color", "color": [65535, 0, 0, 1000, 2000], "colorRes": "16Bit", "fadeMs": 2000})
    assert list(state["requests"][0]["params"]["item"][0]) == ["out", "op", "fc", "durMs"]
    assert list(state["requests"][1]["params"]) == ["op", "color", "colorRes", "fadeMs"]


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["null", "string", "list", "missing_code", "null_code", "string_code", "list_code", "object_code", "true", "false", "float"])
async def test_malformed_error_envelopes_are_sanitized(controller, kind):
    client, state = controller
    url = f"{client.base_url}/v1.9/?user=oper&auth={client.auth['auth']}"
    state["error_envelope"] = {
        "null": None, "string": url, "list": [url], "missing_code": {"msg": url},
        "null_code": {"code": None}, "string_code": {"code": url},
        "list_code": {"code": [url]}, "object_code": {"code": {"url": url}},
        "true": {"code": True}, "false": {"code": False}, "float": {"code": 10.0},
    }[kind]
    with pytest.raises(api.PixLiteError) as caught:
        await client.read("status")
    assert caught.value.args == ("Invalid controller error response",)
    assert caught.value.code is None
    assert client.auth["auth"] not in str(caught.value)


@pytest.mark.asyncio
async def test_unknown_integer_error_ignores_server_message(controller):
    client, state = controller
    state["error_envelope"] = {"code": 123456, "msg": f"http://controller/?auth={client.auth['auth']}"}
    with pytest.raises(api.PixLiteError) as caught:
        await client.read("status")
    assert caught.value.code == 123456
    assert str(caught.value) == "Controller rejected statusRead (code 123456)"


@pytest.mark.asyncio
@pytest.mark.parametrize("field,value", [("prodName", None), ("prodName", 1), ("prodName", []), ("prodName", {}), ("prodName", False), ("prodName", ""), ("prodName", " "), ("nickname", None), ("nickname", 1), ("nickname", []), ("nickname", {}), ("nickname", False), ("ver", None), ("ver", []), ("ver", 1)])
async def test_invalid_metadata_does_not_publish_constants(controller, field, value):
    client, state = controller
    await client.initialize()
    before = client.constants
    if field == "nickname":
        state["version"] = {"apiVer": [{"maj": "v1", "min": [0, 9]}], "nickname": value}
    else:
        state["constants"] = {"dev": dict(before["dev"])}
        if field == "ver":
            state["constants"]["ver"] = value
        else:
            state["constants"]["dev"][field] = value
    with pytest.raises(api.PixLiteError):
        await client.initialize()
    assert client.constants is before


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", ["apiVer", "prodName"])
async def test_missing_metadata_is_a_protocol_error(controller, missing):
    client, state = controller
    if missing == "apiVer":
        state["version"] = {}
    else:
        state["constants"] = {"dev": {"prodFamilyName": "PixLite Mk3", "macAddr": "AC-DE-48-00-00-80"}}
    expected = "Invalid API version response" if missing == "apiVer" else "Invalid controller product name"
    with pytest.raises(api.PixLiteError, match=f"^{expected}$") as caught:
        await client.initialize()
    assert type(caught.value) is api.PixLiteError
    assert client.constants == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("versions", [None, {}, "v1.9", [None], [1], [{}],
    [{"maj": "v1", "min": None}], [{"maj": "v1", "min": "09"}],
    [{"maj": "v1", "min": [9]}], [{"maj": "v1", "min": [9, 0]}],
    [{"maj": "v1", "min": [-1, 9]}], [{"maj": "v1", "min": [False, 9]}],
    [{"maj": "v1", "min": [0, "9"]}], [{"maj": None, "min": [0, 9]}]])
async def test_malformed_version_types_are_sanitized(versions):
    client = api.PixLiteClient(None, "controller.local", password="secret")
    client._exchange = AsyncMock(return_value={"apiVer": versions})
    with pytest.raises(api.PixLiteError) as error:
        await client.initialize()
    assert not isinstance(error.value, api.UnsupportedDevice)
    assert "secret" not in str(error.value)
    assert client.auth["auth"] not in str(error.value)

@pytest.mark.asyncio
@pytest.mark.parametrize("dev", [None, [], "controller", {}, {"macAddr": None},
    {"macAddr": 123}, {"macAddr": "invalid"}, {"macAddr": "00-00-00-00-00-00"},
    {"macAddr": "AA:BB-CC:DD:EE:FF"}])
async def test_malformed_identity_is_protocol_error(dev):
    client = api.PixLiteClient(None, "controller.local")
    client._exchange = AsyncMock(return_value={"apiVer": [{"maj": "v1", "min": [0, 9]}]})
    client.read = AsyncMock(return_value={"dev": dev})
    with pytest.raises(api.PixLiteError):
        await client.initialize()

@pytest.mark.parametrize("mac", ["AC-DE-48-00-00-80", "ac:de:48:00:00:80", "ACDE48000080"])
@pytest.mark.asyncio
async def test_identity_normalization(mac):
    client = api.PixLiteClient(None, "controller.local")
    client._exchange = AsyncMock(return_value={"apiVer": [{"maj": "v1", "min": [0, 9]}]})
    client.read = AsyncMock(return_value={"dev": {"prodFamilyName": "PixLite Mk3", "prodName": "PixLite Mk3", "macAddr": mac}})
    await client.initialize()
    assert client.unique_id == "acde48000080"

@pytest.mark.asyncio
async def test_invalid_json_is_sanitized(controller):
    client, state = controller
    state["invalid_json"] = True
    with pytest.raises(api.PixLiteError) as error:
        await client.read("status")
    assert str(error.value) == "Unable to communicate with controller"
    assert client.auth["auth"] not in str(error.value)

@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["prodName", "nickname"])
@pytest.mark.parametrize("value", [None, 12, {}, [], True])
async def test_malformed_product_metadata_is_protocol_error(field, value):
    client = api.PixLiteClient(None, "controller.local", password="secret")
    version = {"apiVer": [{"maj": "v1", "min": [0, 9]}]}
    dev = {"prodFamilyName": "PixLite Mk3", "prodName": "PixLite Mk3", "macAddr": "AC-DE-48-00-00-80"}
    (version if field == "nickname" else dev)[field] = value
    client._exchange = AsyncMock(return_value=version)
    client.read = AsyncMock(return_value={"dev": dev})
    with pytest.raises(api.PixLiteError) as error:
        await client.initialize()
    assert "secret" not in str(error.value)
    assert client.auth["auth"] not in str(error.value)

@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["null_error", "string_error", "list_error", "missing_code", "null_code",
                                 "string_code", "list_code", "object_code", "true_code", "false_code", "float_code"])
async def test_malformed_error_codes_never_reflect_authenticated_urls(controller, kind):
    client, state = controller
    leaked_url = f"{client.base_url}/v1.9/?user=oper&auth={client.auth['auth']}"
    state["error_envelope"] = {
        "null_error": None, "string_error": leaked_url, "list_error": [leaked_url],
        "missing_code": {"msg": leaked_url}, "null_code": {"code": None},
        "string_code": {"code": leaked_url}, "list_code": {"code": [leaked_url]},
        "object_code": {"code": {"request_url": leaked_url}}, "true_code": {"code": True},
        "false_code": {"code": False}, "float_code": {"code": 10.0},
    }[kind]
    with pytest.raises(api.PixLiteError) as error:
        await client.read("status")
    assert str(error.value) == "Invalid controller error response"
    assert error.value.code is None
    assert leaked_url not in str(error.value)
    assert client.auth["auth"] not in str(error.value)

@pytest.mark.asyncio
async def test_future_integer_error_ignores_untrusted_message(controller):
    client, state = controller
    state["error_envelope"] = {"code": 999, "msg": f"http://controller/?auth={client.auth['auth']}"}
    with pytest.raises(api.PixLiteError) as error:
        await client.read("status")
    assert error.value.code == 999
    assert str(error.value) == "Controller rejected statusRead (code 999)"
    assert client.auth["auth"] not in str(error.value)
