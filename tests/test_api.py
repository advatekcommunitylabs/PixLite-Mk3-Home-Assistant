"""Exercise the actual HTTP client against an in-process controller simulator."""
import asyncio
import importlib.util
from pathlib import Path

import aiohttp
from aiohttp import web
import pytest
import pytest_asyncio

spec = importlib.util.spec_from_file_location("pixlite_api", Path(__file__).parents[1] / "custom_components/advatek_pixlite/api.py")
api = importlib.util.module_from_spec(spec)
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
                return web.json_response({"resp": "version", "result": {"apiVer": [{"maj": "v1", "min": state["minor"]}]}})
            assert request.path == "/v1.9/"
            body = await request.json()
            assert next(iter(body)) == "req"
            assert request.query["auth"] == api.password_hash("secret")
            assert request.query["user"] == "oper"
            state["requests"].append(body)
            if state["http"] != 200:
                return web.Response(status=state["http"])
            response = {"resp": body["req"]}
            if state["error"]:
                response["err"] = {"code": state["error"], "msg": "test"}
            elif body["req"] == "constantRead":
                response["result"] = {"constant": {"dev": {"prodFamilyName": "PixLite Mk3", "macAddr": "AC-DE-48-00-00-80"}}}
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
