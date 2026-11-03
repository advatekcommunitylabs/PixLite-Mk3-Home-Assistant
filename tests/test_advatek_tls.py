"""Exercise the vendor TLS path with synthetic certificates and raw TLS peers."""

import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
import hashlib
import importlib.util
import json
from pathlib import Path
import ssl
import sys
import threading

import aiohttp
from cryptography import x509
from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID, ObjectIdentifier
from OpenSSL import crypto
import pytest

spec = importlib.util.spec_from_file_location(
    "vendor_tls_api",
    Path(__file__).parents[1] / "custom_components/advatek_pixlite/_client/__init__.py",
)
api = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = api
spec.loader.exec_module(api)
tls = sys.modules[spec.name + "._tls"]
MAC = "acde48000080"
OTHER_MAC = "acde48000082"


def der(cert):
    return cert.public_bytes(serialization.Encoding.DER)


@pytest.fixture(scope="module")
def keys():
    return (
        rsa.generate_private_key(65537, 2048),
        rsa.generate_private_key(65537, 2048),
        ec.generate_private_key(ec.SECP256R1()),
    )


def make_chain(keys, defect="", mac=MAC):
    now = datetime.now(UTC)
    root_key, issuer_key, leaf_key = keys
    if defect == "weak_key":
        leaf_key = rsa.generate_private_key(65537, 1024)
    names = [
        x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])
        for name in ("Synthetic root", "Synthetic issuing CA", mac)
    ]
    if defect == "missing_cn":
        names[2] = x509.Name([x509.NameAttribute(NameOID.ORGANIZATION_NAME, mac)])
    elif defect == "duplicate_cn":
        names[2] = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, mac)] * 2)
    elif defect == "wrong_cn":
        names[2] = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, OTHER_MAC)])
    certificates = []
    for index, key in enumerate((root_key, issuer_key, leaf_key)):
        is_ca = index < 2
        parent = max(0, index - 1)
        parent_key = (root_key, issuer_key)[parent]
        before, after = now - timedelta(days=1), now + timedelta(days=30)
        if defect == f"expired_{index}":
            after = now - timedelta(hours=1)
        if defect == f"future_{index}":
            before = now + timedelta(hours=1)
        if defect == "near_expiry" and index == 2:
            after = now + timedelta(seconds=5)
        builder = (
            x509.CertificateBuilder().subject_name(names[index])
            .issuer_name(names[parent]).public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(before).not_valid_after(after)
            .add_extension(x509.BasicConstraints(
                ca=is_ca and not (defect == "non_ca" and index == 1),
                path_length=(0 if index == 1 or defect == "path_length" else 3) if is_ca and not (defect == "non_ca" and index == 1) else None,
            ), critical=True)
            .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), False)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(parent_key.public_key()), False)
        )
        if is_ca or (defect == "leaf_ku" and index == 2):
            builder = builder.add_extension(x509.KeyUsage(
                digital_signature=True, content_commitment=False,
                key_encipherment=False, data_encipherment=False,
                key_agreement=False, key_cert_sign=is_ca, crl_sign=is_ca,
                encipher_only=False, decipher_only=False,
            ), True)
        if index == 2:
            eku = [ExtendedKeyUsageOID.ANY_EXTENDED_KEY_USAGE]
            if defect == "leaf_eku":
                eku = [ExtendedKeyUsageOID.SERVER_AUTH]
            builder = builder.add_extension(x509.ExtendedKeyUsage(eku), False)
        elif defect == f"ca_eku_{index}":
            builder = builder.add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.CLIENT_AUTH]), False)
        if defect == "san" and index == 2:
            builder = builder.add_extension(x509.SubjectAlternativeName([x509.DNSName(mac)]), False)
        if defect == f"netscape_{index}":
            builder = builder.add_extension(x509.UnrecognizedExtension(tls._NETSCAPE_TYPE, b"\x03\x02\x00\x40"), False)
        if defect == "unknown_critical" and index == 2:
            builder = builder.add_extension(x509.UnrecognizedExtension(ObjectIdentifier("1.2.3.4.5"), b"\x05\x00"), True)
        if defect == "explicit_policy" and index == 1:
            builder = builder.add_extension(x509.PolicyConstraints(require_explicit_policy=0, inhibit_policy_mapping=None), True)
        if defect in ("private_expired", "private_future", "private_near_expiry") and index == 2:
            builder = builder.add_extension(x509.PrivateKeyUsagePeriod(
                not_before=now + timedelta(hours=1) if defect == "private_future" else now - timedelta(days=1),
                not_after=(now - timedelta(hours=1) if defect == "private_expired" else now + timedelta(seconds=5) if defect == "private_near_expiry" else now + timedelta(days=1)),
            ), False)
        certificates.append(builder.sign(parent_key, hashes.SHA256()))
    if defect == "bad_signature":
        data = bytearray(der(certificates[2]))
        data[-1] ^= 1
        certificates[2] = x509.load_der_x509_certificate(bytes(data))
    return certificates, leaf_key


def trust(monkeypatch, certificates):
    monkeypatch.setattr(tls, "ROOT_PEM", certificates[0].public_bytes(serialization.Encoding.PEM))
    monkeypatch.setattr(tls, "ROOT_SHA256", hashlib.sha256(der(certificates[0])).hexdigest())


def wire(certificates):
    return tuple(der(cert) for cert in reversed(certificates))


def test_accepts_only_the_completed_pinned_path(keys, monkeypatch):
    certs, _ = make_chain(keys)
    trust(monkeypatch, certs)
    for chain in (wire(certs), wire(certs)[:2]):
        assert tls._validate_chain(chain, MAC, datetime.now(UTC) + timedelta(seconds=11)) == hashlib.sha256(der(certs[2])).digest()


@pytest.mark.parametrize("defect", [
    "missing_cn", "duplicate_cn", "wrong_cn", "leaf_ku", "leaf_eku", "san",
    "ca_eku_0", "ca_eku_1", "netscape_0", "netscape_1", "netscape_2",
    "expired_0", "expired_1", "expired_2", "future_0", "future_1", "future_2",
    "near_expiry", "private_expired", "private_future", "private_near_expiry",
    "weak_key", "non_ca", "path_length", "unknown_critical", "explicit_policy", "bad_signature",
])
def test_rejects_unacceptable_paths(keys, monkeypatch, defect):
    certs, _ = make_chain(keys, defect)
    trust(monkeypatch, certs)
    with pytest.raises(tls.CertificateError):
        tls._validate_chain(wire(certs), MAC, datetime.now(UTC) + timedelta(seconds=11))


@pytest.mark.parametrize("defect", ["untrusted", "extra", "duplicate", "missing", "malformed", "oversized", "root_hash"])
def test_rejects_untrusted_or_malformed_inputs(keys, monkeypatch, defect):
    certs, _ = make_chain(keys)
    trust(monkeypatch, certs)
    chain = wire(certs)
    if defect == "untrusted":
        other, _ = make_chain(keys)
        trust(monkeypatch, other)
    elif defect == "extra":
        chain += (chain[0],)
    elif defect == "duplicate":
        chain = (chain[0], chain[0])
    elif defect == "missing":
        chain = chain[:1]
    elif defect == "malformed":
        chain = (b"invalid", chain[1])
    elif defect == "oversized":
        chain = (b"0" * 16385, chain[1])
    elif defect == "root_hash":
        monkeypatch.setattr(tls, "ROOT_SHA256", "0" * 64)
    with pytest.raises(tls.CertificateError):
        tls._validate_chain(chain, MAC, datetime.now(UTC) + timedelta(seconds=11))


@pytest.mark.parametrize("error", [UnsupportedAlgorithm("unsupported"), crypto.Error("invalid")])
def test_parser_domain_errors_have_fixed_diagnostics(keys, monkeypatch, error):
    certs, _ = make_chain(keys)

    def unsupported(_):
        raise error

    monkeypatch.setattr(tls.x509, "load_der_x509_certificate", unsupported)
    with pytest.raises(tls.CertificateError) as caught:
        tls._validate_chain(wire(certs), MAC, datetime.now(UTC) + timedelta(seconds=11))
    assert "unsupported" not in str(caught.value)


@asynccontextmanager
async def peer(tmp_path, certificates, key, *, drop=False, redirect=False):
    cert_file = tmp_path / (certificates[2].serial_number.__str__() + ".pem")
    key_file = cert_file.with_suffix(".key")
    cert_file.write_bytes(b"".join(c.public_bytes(serialization.Encoding.PEM) for c in reversed(certificates)))
    key_file.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert_file, key_file)
    received, connections, tasks = [], [], set()

    async def handle(reader, writer):
        task = asyncio.current_task()
        tasks.add(task)
        connections.append(writer)
        try:
            data = await reader.read(65536)
            if not data:
                return
            received.append(data)
            if drop:
                return
            header, body = data.split(b"\r\n\r\n", 1)
            if header.startswith(b"GET "):
                result = {"resp": "version", "result": {"apiVer": [{"maj": "v1", "min": [0, 9]}]}}
            else:
                length = next(int(line.split(b":", 1)[1]) for line in header.split(b"\r\n") if line.lower().startswith(b"content-length:"))
                if len(body) < length:
                    body += await reader.readexactly(length - len(body))
                req = json.loads(body)["req"]
                result = {"resp": req, "result": {"constant": {"dev": {"prodFamilyName": "PixLite Mk3", "prodName": "PixLite Mk3", "macAddr": list(certificates[2].subject)[0].value}}}}
            payload = json.dumps(result).encode()
            status = b"302 Found\r\nLocation: http://127.0.0.1:1/" if redirect else b"200 OK"
            writer.write(b"HTTP/1.1 " + status + b"\r\nContent-Type: application/json\r\nConnection: close\r\nContent-Length: " + str(len(payload)).encode() + b"\r\n\r\n" + payload)
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()
            tasks.discard(task)

    server = await asyncio.start_server(handle, "127.0.0.1", 0, ssl=context)
    try:
        yield server.sockets[0].getsockname()[1], received, connections
    finally:
        server.close()
        await server.wait_closed()
        for writer in connections:
            writer.close()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


@pytest.mark.asyncio
async def test_concurrent_clients_use_independent_pins_and_fresh_connections(keys, monkeypatch, tmp_path):
    first, key = make_chain(keys)
    second, _ = make_chain(keys, mac=OTHER_MAC)
    # Both devices share one trusted root and issuing CA.
    second[:2] = first[:2]
    trust(monkeypatch, first)
    async with peer(tmp_path, first, key) as a, peer(tmp_path, second, key) as b:
        async with aiohttp.ClientSession() as session:
            clients = [api.PixLiteClient(session, "127.0.0.1", "oper", "fixture-secret", True, p[0], m) for p, m in ((a, MAC), (b, OTHER_MAC))]
            await asyncio.gather(*(c.initialize() for c in clients))
            await asyncio.gather(*(c.read("constant") for c in clients))
            assert [c.unique_id for c in clients] == [MAC, OTHER_MAC]
        for _, data, connections in (a, b):
            assert len(data) == 3
            assert len(connections) == 4  # One certificate capture, three API connections.
            assert b"auth=" not in data[0]
            assert api.password_hash("fixture-secret").encode() in data[1]


@pytest.mark.asyncio
@pytest.mark.parametrize("defect", ["wrong_cn", "leaf_eku", "leaf_ku", "san", "netscape_1", "expired_2", "private_expired", "unknown_critical", "explicit_policy"])
async def test_rejected_peer_receives_zero_application_bytes(keys, monkeypatch, tmp_path, defect):
    certs, key = make_chain(keys, defect)
    trust(monkeypatch, certs)
    async with peer(tmp_path, certs, key) as (port, received, _):
        async with aiohttp.ClientSession() as session:
            client = api.PixLiteClient(session, "127.0.0.1", "oper", "fixture-secret", True, port, MAC)
            with pytest.raises(api.InvalidCertificate):
                await client.initialize()
        assert received == []


@pytest.mark.asyncio
async def test_substituted_leaf_fails_before_http_and_does_not_retry(keys, monkeypatch, tmp_path):
    accepted, key = make_chain(keys)
    different, _ = make_chain(keys)
    trust(monkeypatch, accepted)
    async with peer(tmp_path, different, key) as (port, received, _):
        async with aiohttp.ClientSession() as session:
            client = api.PixLiteClient(session, "127.0.0.1", "oper", "fixture-secret", True, port, MAC)
            client._tls._chain = wire(accepted)
            with pytest.raises(api.InvalidCertificate):
                await client.request("stateWrite", {"state": "live"})
            assert client._tls._chain is None
        assert received == []


@pytest.mark.asyncio
@pytest.mark.parametrize("redirect", [False, True])
async def test_operator_post_never_replays_or_follows_redirects(keys, monkeypatch, tmp_path, redirect):
    certs, key = make_chain(keys)
    trust(monkeypatch, certs)
    async with peer(tmp_path, certs, key, drop=not redirect, redirect=redirect) as (port, received, _):
        async with aiohttp.ClientSession() as session:
            client = api.PixLiteClient(session, "127.0.0.1", "oper", "fixture-secret", True, port, MAC)
            with pytest.raises(api.PixLiteError):
                await client.request("stateWrite", {"state": "live"})
        assert len(received) == 1


@pytest.mark.asyncio
async def test_cancelled_validator_cannot_publish_cache_or_send_http(keys, monkeypatch, tmp_path):
    certs, key = make_chain(keys)
    trust(monkeypatch, certs)
    entered, finish, done = threading.Event(), threading.Event(), threading.Event()
    original = tls._validate_chain

    def paused(*args):
        entered.set()
        finish.wait(5)
        try:
            return original(*args)
        finally:
            done.set()

    monkeypatch.setattr(tls, "_validate_chain", paused)
    async with peer(tmp_path, certs, key) as (port, received, _):
        async with aiohttp.ClientSession() as session:
            client = api.PixLiteClient(session, "127.0.0.1", "oper", "fixture-secret", True, port, MAC)
            task = asyncio.create_task(client.initialize())
            try:
                assert await asyncio.to_thread(entered.wait, 3)
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
            finally:
                finish.set()
            assert await asyncio.to_thread(done.wait, 3)
            assert client._tls._chain is None
        assert received == []


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["trust_env", "auth"])
async def test_proxy_and_default_auth_are_rejected_before_tls(monkeypatch, kind):
    async def forbidden(*args):
        pytest.fail("Untrusted session reached the TLS peer")
    monkeypatch.setattr(tls, "_capture_chain", forbidden)
    kwargs = {"trust_env": True} if kind == "trust_env" else {"auth": aiohttp.BasicAuth("user", "secret")}
    async with aiohttp.ClientSession(**kwargs) as session:
        client = api.PixLiteClient(session, "127.0.0.1", use_ssl=True, expected_mac=MAC)
        with pytest.raises(api.InvalidCertificate):
            await client.initialize()


@pytest.mark.asyncio
@pytest.mark.parametrize("defect", ["near_expiry", "private_near_expiry", "expired_1"])
async def test_cached_chain_expiry_blocks_all_http(keys, monkeypatch, tmp_path, defect):
    certs, key = make_chain(keys, defect)
    trust(monkeypatch, certs)
    async with peer(tmp_path, certs, key) as (port, received, connections):
        async with aiohttp.ClientSession() as session:
            client = api.PixLiteClient(session, "127.0.0.1", "oper", "fixture-secret", True, port, MAC)
            client._tls._chain = wire(certs)
            with pytest.raises(api.InvalidCertificate):
                await client.request("modeLive")
            assert client._tls._chain is None
        assert received == []
        assert connections == []


@pytest.mark.asyncio
async def test_renewed_peer_is_seen_on_next_request_after_cached_expiry(keys, monkeypatch, tmp_path):
    certs, key = make_chain(keys)
    old, _ = make_chain(keys, "expired_2")
    old[:2] = certs[:2]
    trust(monkeypatch, certs)
    async with peer(tmp_path, certs, key) as (port, received, connections):
        async with aiohttp.ClientSession() as session:
            client = api.PixLiteClient(session, "127.0.0.1", "oper", "fixture-secret", True, port, MAC)
            client._tls._chain = wire(old)
            with pytest.raises(api.InvalidCertificate):
                await client.request("modeLive")
            assert client._tls._chain is None
            assert not received and not connections
            await client.initialize()
            assert len(received) == 2


@pytest.mark.asyncio
async def test_total_timeout_covers_validation_without_late_http(keys, monkeypatch, tmp_path):
    certs, key = make_chain(keys)
    trust(monkeypatch, certs)
    entered, finish, done = threading.Event(), threading.Event(), threading.Event()
    original = tls._validate_chain

    def paused(*args):
        entered.set()
        finish.wait(5)
        try:
            return original(*args)
        finally:
            done.set()

    monkeypatch.setattr(tls, "_validate_chain", paused)
    monkeypatch.setattr(api, "REQUEST_SECONDS", 0.1)
    async with peer(tmp_path, certs, key) as (port, received, _):
        async with aiohttp.ClientSession() as session:
            client = api.PixLiteClient(session, "127.0.0.1", "oper", "fixture-secret", True, port, MAC)
            try:
                with pytest.raises(api.PixLiteError):
                    await client.request("modeLive")
                assert entered.is_set()
            finally:
                finish.set()
                assert await asyncio.to_thread(done.wait, 3)
            assert client._tls._chain is None
        assert received == []


@pytest.mark.asyncio
async def test_cancellation_during_handshake_closes_connection(monkeypatch):
    arrived, closed = asyncio.Event(), asyncio.Event()
    received = []

    async def stall(reader, writer):
        arrived.set()
        try:
            while data := await reader.read(65536):
                received.append(data)
        finally:
            writer.close()
            await writer.wait_closed()
            closed.set()

    server = await asyncio.start_server(stall, "127.0.0.1", 0)
    try:
        async with aiohttp.ClientSession() as session:
            port = server.sockets[0].getsockname()[1]
            client = api.PixLiteClient(session, "127.0.0.1", use_ssl=True, port=port, expected_mac=MAC)
            task = asyncio.create_task(client.request("modeLive"))
            await asyncio.wait_for(arrived.wait(), 2)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            await asyncio.wait_for(closed.wait(), 2)
            assert client._tls._chain is None
            assert not any(b"POST" in data or b"auth=" in data for data in received)
    finally:
        server.close()
        await server.wait_closed()


@pytest.mark.asyncio
async def test_one_rejected_device_does_not_interrupt_its_peer(keys, monkeypatch, tmp_path):
    certs, key = make_chain(keys)
    trust(monkeypatch, certs)
    async with peer(tmp_path, certs, key) as (port, received, _):
        async with aiohttp.ClientSession() as session:
            good = api.PixLiteClient(session, "127.0.0.1", "oper", "fixture-secret", True, port, MAC)
            bad = api.PixLiteClient(session, "127.0.0.1", "oper", "fixture-secret", True, port, OTHER_MAC)
            results = await asyncio.gather(good.initialize(), bad.initialize(), return_exceptions=True)
            assert isinstance(results[1], api.InvalidCertificate)
            assert good.unique_id == MAC
            await good.read("constant")
        assert len(received) == 3


@pytest.mark.asyncio
async def test_session_middleware_cannot_change_the_verified_url(keys, monkeypatch, tmp_path):
    certs, key = make_chain(keys)
    trust(monkeypatch, certs)

    async def forbidden(request, handler):
        pytest.fail("Caller middleware must not run in the vendor TLS exchange")

    async with peer(tmp_path, certs, key) as (port, received, _):
        async with aiohttp.ClientSession(middlewares=(forbidden,)) as session:
            client = api.PixLiteClient(session, "127.0.0.1", "oper", "fixture-secret", True, port, MAC)
            await client.initialize()
        assert len(received) == 2


@pytest.mark.parametrize("value", ["", "000000000000", "abde48000080", "ac:de:48:00:00", "acde4800008z"])
def test_invalid_mac(value):
    with pytest.raises(api.InvalidMAC):
        tls.normalize_mac(value)


def test_canonical_mac():
    for value in (MAC, "AC:DE:48:00:00:80", "ac-de-48-00-00-80"):
        assert tls.normalize_mac(value) == MAC
