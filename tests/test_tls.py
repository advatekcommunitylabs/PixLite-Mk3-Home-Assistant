"""Check verified TLS before controller data or credentials can be exchanged."""

import importlib.util
from pathlib import Path
import ssl
import sys

import aiohttp
from aiohttp import web
import pytest
import pytest_asyncio

pytestmark = pytest.mark.asyncio

spec = importlib.util.spec_from_file_location(
    "pixlite_tls_api",
    Path(__file__).parents[1] / "custom_components/advatek_pixlite/_client/__init__.py",
)
api = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = api
spec.loader.exec_module(api)
FIXTURES = Path(__file__).parent / "fixtures/tls"


@pytest_asyncio.fixture
async def tls_controller(request):
    certificate = request.param
    requests = []

    async def handler(request):
        requests.append(request.path)
        if request.method == "GET":
            assert not request.query
            return web.json_response(
                {"resp": "version", "result": {"apiVer": [{"maj": "v1", "min": [0, 9]}]}}
            )
        assert request.query["user"] == "oper"
        assert request.query["auth"] == api.password_hash("fixture-secret")
        return web.json_response(
            {"resp": "constantRead", "result": {"constant": {"dev": {
                "prodFamilyName": "PixLite Mk3", "macAddr": "acde48000080"
            }}}}
        )

    app = web.Application()
    app.router.add_route("*", "/{path:.*}", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(FIXTURES / f"{certificate}.pem", FIXTURES / "server-key.pem")
    site = web.TCPSite(runner, "127.0.0.1", 0, ssl_context=context)
    await site.start()
    try:
        yield site._server.sockets[0].getsockname()[1], requests
    finally:
        await runner.cleanup()


@pytest.mark.parametrize("tls_controller", ["valid"], indirect=True)
async def test_trusted_https_initializes_and_authenticates(tls_controller):
    port, requests = tls_controller
    context = ssl.create_default_context(cafile=FIXTURES / "root.pem")
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=context)) as session:
        client = api.PixLiteClient(session, "127.0.0.1", "oper", "fixture-secret", use_ssl=True, port=port)
        await client.initialize()
        assert client.unique_id == "acde48000080"
    assert requests == ["/ver", "/v1.9/"]


@pytest.mark.parametrize(
    ("tls_controller", "trusted", "reason"),
    [
        ("valid", False, "certificate_untrusted"),
        ("identity", True, "certificate_identity"),
        ("purpose", True, "certificate_purpose"),
        ("expired", True, "certificate_validity"),
    ],
    indirect=["tls_controller"],
)
async def test_rejected_tls_sends_no_http_or_credentials(tls_controller, trusted, reason):
    port, requests = tls_controller
    context = ssl.create_default_context(cafile=FIXTURES / "root.pem" if trusted else None)
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=context)) as session:
        client = api.PixLiteClient(session, "127.0.0.1", "oper", "fixture-secret", use_ssl=True, port=port)
        with pytest.raises(api.InvalidCertificate) as error:
            await client.initialize()
        assert error.value.reason == reason
        assert "127.0.0.1" not in str(error.value)
        assert "fixture-secret" not in str(error.value)
        assert api.password_hash("fixture-secret") not in str(error.value)
        assert error.value.__suppress_context__
    assert not requests


@pytest.mark.parametrize("tls_controller", ["valid"], indirect=True)
async def test_caller_pin_mismatch_without_vendor_profile_is_a_certificate_error(tls_controller):
    port, requests = tls_controller
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=aiohttp.Fingerprint(bytes(32)))) as session:
        client = api.PixLiteClient(session, "127.0.0.1", "oper", "fixture-secret", use_ssl=True, port=port)
        with pytest.raises(api.InvalidCertificate):
            await client.initialize()
    assert not requests


@pytest.mark.parametrize(("use_ssl", "port", "expected"), [
    (True, None, "https://controller:4443"),
    (True, 8443, "https://controller:8443"),
    (False, None, "http://controller:80"),
])
async def test_documented_ports(use_ssl, port, expected):
    async with aiohttp.ClientSession() as session:
        assert api.PixLiteClient(session, "controller", use_ssl=use_ssl, port=port).base_url == expected
