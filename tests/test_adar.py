"""Verify the ADAR wire contract and bounded discovery without LAN traffic."""

import asyncio
import importlib.util
import json
import socket
import struct
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "adar_client_test",
    Path(__file__).parents[1] / "custom_components/advatek_pixlite/_adar/__init__.py",
)
adar = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = adar
_SPEC.loader.exec_module(adar)


@pytest.fixture
def device_data():
    return {
        "prodFamily": 0x50697833,
        "oem": 0,
        "macAddr": "E0B6F5E04980",
        "ipAddr": "192.0.2.10",
        "prodName": "PixLite A4-S Mk3",
        "prodFamilyName": "PixLite Mk3",
        "nickname": "Garden",
        "inEmergRecovery": False,
        "hasWebIf": True,
        "apiVer": [{"maj": "v1", "min": [0, 9]}],
    }


def packet(data):
    return struct.pack("!8sHH", b"DiscProt", 0x2102, 0x0101) + json.dumps(data).encode()


def test_request_layout_and_exclusions():
    request = adar.discovery_request(("E0-B6-F5-E0-49-80",))
    assert len(request) == 40
    assert (
        request[:34]
        == b"DiscProt\x12\x01\x01\x01Pix3\x00\x00\x00\x00"
        + bytes(6)
        + b"\xff" * 6
        + b"\x00\x01"
    )
    assert request[34:] == bytes.fromhex("E0B6F5E04980")
    with pytest.raises(ValueError):
        adar.discovery_request(("e0b6f5e04980",) * 51)


@pytest.mark.parametrize(
    "mac", ["", "not a MAC", "000000000000", "FFFFFFFFFFFF", "010000000001"]
)
def test_invalid_mac(mac):
    with pytest.raises(ValueError):
        adar.normalize_mac(mac)


def test_documented_response(device_data):
    device = adar.parse_response(packet(device_data), "192.0.2.10")
    assert device.mac == "e0b6f5e04980"
    assert device.eligible
    assert device.nickname == "Garden"


@pytest.mark.parametrize(
    "changes",
    [
        {"prodFamily": True},
        {"prodFamily": 123},
        {"oem": True},
        {"oem": 1},
        {"prodFamilyName": "Other"},
        {"macAddr": "E0-B6-F5-E0-49-80"},
        {"macAddr": None},
        {"ipAddr": None},
        {"ipAddr": 1},
        {"ipAddr": "0.0.0.0"},
        {"ipAddr": "239.1.2.3"},
        {"ipAddr": "255.255.255.255"},
        {"ipAddr": "192.0.2.11"},
        {"ipAddr": "::1"},
        {"prodName": ""},
        {"prodName": ["PixLite"]},
        {"nickname": "x" * 64},
        {"nickname": "bad\nname"},
        {"hasWebIf": 1},
        {"inEmergRecovery": None},
    ],
)
def test_invalid_response_fields(device_data, changes):
    assert adar.parse_response(packet(device_data | changes), "192.0.2.10") is None


@pytest.mark.parametrize(
    "raw",
    [
        b"",
        b"DiscProt",
        b"x" * 9000,
        b"DiscProt\x21\x02\x01\x00{}",
        b"DiscProt\x12\x01\x01\x01{}",
        b"DiscProt\x21\x02\x01\x01\xff",
    ],
)
def test_invalid_frame(raw):
    assert adar.parse_response(raw, "192.0.2.10") is None


@pytest.mark.parametrize(
    "versions,supported",
    [
        (None, False),
        ([None], False),
        ([{"maj": "v1", "min": None}], False),
        ([{"maj": "v1", "min": [True, 9]}], False),
        ([{"maj": "v1", "min": [0, 8]}], False),
        ([{"maj": "v1", "min": [10, 12]}], False),
        ([{"maj": "v1", "min": [9, 9]}], True),
        ([{"maj": "other", "min": [0, 99]}, {"maj": "v1", "min": [0, 10]}], True),
    ],
)
def test_api_range(device_data, versions, supported):
    device = adar.parse_response(
        packet(device_data | {"apiVer": versions}), "192.0.2.10"
    )
    assert device.api_supported is supported


def test_recovery_without_optional_fields_is_not_eligible(device_data):
    device_data.update(inEmergRecovery=True)
    device_data.pop("apiVer")
    device_data.pop("nickname")
    assert not adar.parse_response(packet(device_data), "192.0.2.10").eligible


def test_socket_interface_and_membership(monkeypatch):
    listener, sender = Mock(), Mock()
    listener.getsockname.return_value = ("0.0.0.0", 12345)
    monkeypatch.setattr(adar.socket, "socket", Mock(side_effect=[listener, sender]))
    assert adar._sockets("192.0.2.1") == (listener, sender)
    listener.bind.assert_called_once_with(("0.0.0.0", 0))
    listener.setsockopt.assert_any_call(
        socket.IPPROTO_IP,
        socket.IP_ADD_MEMBERSHIP,
        socket.inet_aton("239.255.251.2") + socket.inet_aton("192.0.2.1"),
    )
    sender.bind.assert_called_once_with(("192.0.2.1", 12345))
    sender.setsockopt.assert_any_call(
        socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton("192.0.2.1")
    )
    sender.setsockopt.assert_any_call(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 255)


def test_socket_creation_failure_closes_listener(monkeypatch):
    listener = Mock()
    monkeypatch.setattr(
        adar.socket, "socket", Mock(side_effect=[listener, OSError("failed")])
    )
    with pytest.raises(OSError):
        adar._sockets("192.0.2.1")
    listener.close.assert_called_once()


@pytest.mark.asyncio
async def test_rounds_switch_to_broadcast_and_exclude_known_devices(
    monkeypatch, device_data
):
    sockets = (Mock(), Mock())
    monkeypatch.setattr(adar, "_sockets", lambda interface: sockets)
    transports = []

    async def endpoint(factory, sock):
        receiver = factory()
        transport = Mock()

        def send(data, address):
            receiver.datagram_received(packet(device_data), ("192.0.2.10", 49151))

        transport.sendto.side_effect = send
        transports.append(transport)
        return transport, receiver

    monkeypatch.setattr(
        asyncio.get_running_loop(), "create_datagram_endpoint", endpoint
    )
    result = await adar.discover(("192.0.2.1",), interval=0.001)
    assert result.complete
    calls = transports[1].sendto.call_args_list
    assert [call.args[1][0] for call in calls] == [
        "239.255.251.1",
        "239.255.251.1",
        "255.255.255.255",
    ]
    assert calls[0].args[0] == adar.discovery_request()
    assert calls[1].args[0] == adar.discovery_request(("e0b6f5e04980",))
    for resource in sockets + tuple(transports):
        resource.close.assert_called_once()


@pytest.mark.asyncio
async def test_cancel_scan_closes_both_transports(monkeypatch):
    sockets = (Mock(), Mock())
    monkeypatch.setattr(adar, "_sockets", lambda interface: sockets)
    transports = []
    ready = asyncio.Event()

    async def endpoint(factory, sock):
        transport = Mock()
        transports.append(transport)
        if len(transports) == 2:
            ready.set()
        return transport, factory()

    monkeypatch.setattr(
        asyncio.get_running_loop(), "create_datagram_endpoint", endpoint
    )
    task = asyncio.create_task(adar.discover(("192.0.2.1",)))
    await ready.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    for resource in sockets + tuple(transports):
        resource.close.assert_called_once()


@pytest.mark.asyncio
async def test_interface_failure_and_conflicting_macs_are_partial(
    monkeypatch, device_data
):
    device = adar.parse_response(packet(device_data), "192.0.2.10")
    other = adar.parse_response(
        packet(device_data | {"ipAddr": "192.0.2.11"}), "192.0.2.11"
    )

    async def scan(address, interval):
        if address == "192.0.2.3":
            raise OSError("offline")
        return adar.DiscoveryResult((device if address == "192.0.2.1" else other,))

    monkeypatch.setattr(adar, "_scan_interface", scan)
    result = await adar.discover(("192.0.2.1", "192.0.2.2", "192.0.2.3"))
    assert not result.complete
    assert not result.devices
    assert result.conflicts == {device.mac}


@pytest.mark.asyncio
async def test_real_udp_loopback_roundtrip(monkeypatch, device_data):
    """Exercise actual UDP sockets using unicast loopback only."""
    device_data["ipAddr"] = "127.0.0.1"
    requests = []

    class Controller(asyncio.DatagramProtocol):
        def connection_made(self, transport):
            self.transport = transport

        def datagram_received(self, data, addr):
            requests.append(data)
            self.transport.sendto(packet(device_data), addr)

    loop = asyncio.get_running_loop()
    controller, _ = await loop.create_datagram_endpoint(
        Controller, local_addr=("127.0.0.1", 0)
    )
    monkeypatch.setattr(adar, "DEVICE_PORT", controller.get_extra_info("sockname")[1])
    monkeypatch.setattr(adar, "DEVICE_GROUP", "127.0.0.1")

    def sockets(interface):
        receiver = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        receiver.bind(("127.0.0.1", 0))
        sender.bind(("127.0.0.1", 0))
        receiver.setblocking(False)
        sender.setblocking(False)
        return receiver, sender

    monkeypatch.setattr(adar, "_sockets", sockets)
    try:
        # Keep the broadcast phase inside the loopback simulator as well.
        real_endpoint = loop.create_datagram_endpoint

        async def endpoint(factory, **kwargs):
            transport, protocol = await real_endpoint(factory, **kwargs)
            sendto = transport.sendto
            transport.sendto = lambda data, addr=None: sendto(
                data, ("127.0.0.1", addr[1])
            )
            return transport, protocol

        monkeypatch.setattr(loop, "create_datagram_endpoint", endpoint)
        result = await adar.discover(("127.0.0.1",), interval=0.02)
        assert result.complete
        assert result.devices[0].host == "127.0.0.1"
        assert requests[0] == adar.discovery_request()
    finally:
        controller.close()


def test_receiver_bounds_and_conflicting_sources(device_data):
    receiver = adar._Receiver()
    receiver.datagram_received(b"invalid", ("192.0.2.10", 49151))
    assert not receiver.devices
    receiver.datagram_received(packet(device_data), ("192.0.2.10", 49151))
    receiver.datagram_received(
        packet(device_data | {"ipAddr": "192.0.2.11"}), ("192.0.2.11", 49151)
    )
    assert receiver.conflicts == {"e0b6f5e04980"}
    for index in range(60):
        data = device_data | {"macAddr": f"E0B6F5{index:06X}"}
        receiver.datagram_received(packet(data), ("192.0.2.10", 49151))
    assert receiver.overflow
    assert len(receiver.devices) == 50


def test_membership_failure_closes_both_sockets(monkeypatch):
    listener, sender = Mock(), Mock()
    listener.bind.side_effect = OSError("cannot bind")
    monkeypatch.setattr(adar.socket, "socket", Mock(side_effect=[listener, sender]))
    with pytest.raises(OSError):
        adar._sockets("192.0.2.1")
    listener.close.assert_called_once()
    sender.close.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("interval", [0, -1, 2, float("nan")])
async def test_invalid_interval(interval):
    with pytest.raises(ValueError):
        await adar.discover((), interval=interval)


@pytest.mark.asyncio
async def test_no_interfaces_is_incomplete():
    assert not (await adar.discover(())).complete


@pytest.mark.asyncio
async def test_unexpected_scan_error_propagates(monkeypatch):
    async def scan(address, interval):
        raise ValueError("unexpected")

    monkeypatch.setattr(adar, "_scan_interface", scan)
    with pytest.raises(ValueError, match="unexpected"):
        await adar.discover(("192.0.2.1",))


@pytest.mark.asyncio
async def test_global_device_limit(monkeypatch):
    async def scan(address, interval):
        offset = 0 if address == "192.0.2.1" else 50
        return adar.DiscoveryResult(
            tuple(
                adar.Device(
                    f"e0b6f5{index:06x}", "192.0.2.10", "PixLite", "", False, True, True
                )
                for index in range(offset, offset + 50)
            )
        )

    monkeypatch.setattr(adar, "_scan_interface", scan)
    result = await adar.discover(("192.0.2.1", "192.0.2.2"))
    assert len(result.devices) == 50
    assert not result.complete


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["overflow", "error", "budget", "endpoint_failure"])
async def test_scan_limits_and_error_cleanup(monkeypatch, device_data, mode):
    sockets = (Mock(), Mock())
    monkeypatch.setattr(adar, "_sockets", lambda interface: sockets)
    transports = []
    round_number = 0

    async def endpoint(factory, sock):
        if mode == "endpoint_failure" and transports:
            raise OSError("cannot create sender")
        receiver = factory()
        transport = Mock()

        def send(data, address):
            nonlocal round_number
            round_number += 1
            if mode == "error":
                receiver.error_received(OSError("unreachable"))
            else:
                for index in range(51 if mode == "overflow" else 1):
                    identity = round_number * 100 + index
                    receiver.datagram_received(
                        packet(device_data | {"macAddr": f"E0B6F5{identity:06X}"}),
                        ("192.0.2.10", 49151),
                    )

        transport.sendto.side_effect = send
        transports.append(transport)
        return transport, receiver

    monkeypatch.setattr(
        asyncio.get_running_loop(), "create_datagram_endpoint", endpoint
    )
    result = await adar.discover(("192.0.2.1",), interval=0.001)
    assert not result.complete
    assert (
        round_number
        == {"overflow": 1, "error": 1, "budget": 6, "endpoint_failure": 0}[mode]
    )
    for resource in sockets + tuple(transports):
        resource.close.assert_called_once()
