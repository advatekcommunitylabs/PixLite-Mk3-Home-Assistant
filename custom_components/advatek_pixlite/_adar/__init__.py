"""Asynchronous, discovery-only Advatek Discovery and Recovery Protocol client."""

import asyncio
import json
import re
import socket
import struct
from dataclasses import dataclass
from ipaddress import IPv4Address

DEVICE_GROUP = "239.255.251.1"
CLIENT_GROUP = "239.255.251.2"
DEVICE_PORT = 49151
MAX_DEVICES = 50
MAX_PACKET = 8192
_HEADER = struct.Struct("!8sHH")
_REQUEST = struct.Struct("!8sHHII6s6sH")
_MAC = re.compile(r"[0-9a-fA-F]{12}")


@dataclass(frozen=True)
class Device:
    """An ADAR identity, independent of authenticated API access."""

    mac: str
    host: str
    model: str
    nickname: str
    recovery: bool
    web: bool
    api_supported: bool

    @property
    def eligible(self) -> bool:
        """Return whether the controller can be offered for API v1.9 setup."""
        return not self.recovery and self.web and self.api_supported


@dataclass(frozen=True)
class DiscoveryResult:
    """Discovered devices and whether every interface scan completed."""

    devices: tuple[Device, ...] = ()
    complete: bool = True
    conflicts: frozenset[str] = frozenset()


def normalize_mac(value: str) -> str:
    """Normalize API or ADAR MAC syntax to a compact, unicast identifier."""
    if not isinstance(value, str):
        raise TypeError("Invalid controller MAC")
    compact = value.replace("-", "").replace(":", "").lower()
    if not _MAC.fullmatch(compact) or compact == "0" * 12 or int(compact[:2], 16) & 1:
        raise ValueError("Invalid controller MAC")
    return compact


def discovery_request(excluded: tuple[str, ...] = ()) -> bytes:
    """Encode the discovery request, including at most fifty excluded MACs."""
    if len(excluded) > MAX_DEVICES:
        raise ValueError("At most fifty MACs can be excluded")
    addresses = tuple(bytes.fromhex(normalize_mac(mac)) for mac in excluded)
    return _REQUEST.pack(
        b"DiscProt",
        0x1201,
        0x0101,
        0x50697833,
        0,
        bytes(6),
        b"\xff" * 6,
        len(addresses),
    ) + b"".join(addresses)


def _supports_api(versions: object) -> bool:
    """Check the inclusive minor range without trusting JSON value types."""
    if not isinstance(versions, list):
        return False
    for version in versions:
        if not isinstance(version, dict) or version.get("maj") != "v1":
            continue
        minor = version.get("min")
        if (
            isinstance(minor, list)
            and len(minor) == 2
            and all(type(v) is int and v >= 0 for v in minor)
            and minor[0] <= 9 <= minor[1]
        ):
            return True
    return False


def parse_response(packet: bytes, source: str) -> Device | None:
    """Decode a bounded response and require its reported IP to match its sender."""
    if not _HEADER.size < len(packet) <= MAX_PACKET:
        return None
    if _HEADER.unpack_from(packet) != (b"DiscProt", 0x2102, 0x0101):
        return None
    try:
        data = json.loads(packet[_HEADER.size :].decode("utf-8"))
        if (
            not isinstance(data, dict)
            or type(data.get("prodFamily")) is not int
            or data["prodFamily"] != 0x50697833
            or type(data.get("oem")) is not int
            or data["oem"] != 0
            or data.get("prodFamilyName") != "PixLite Mk3"
        ):
            return None
        mac = data.get("macAddr")
        if not isinstance(mac, str) or not _MAC.fullmatch(mac):
            return None
        mac = normalize_mac(mac)
        if not isinstance(data.get("ipAddr"), str):
            return None
        host = IPv4Address(data["ipAddr"])
        if (
            host.is_unspecified
            or host.is_multicast
            or int(host) == 0xFFFFFFFF
            or str(host) != source
        ):
            return None
        model, nickname = data.get("prodName"), data.get("nickname", "")
        if (
            not isinstance(model, str)
            or not model
            or not isinstance(nickname, str)
            or any(
                len(value) > 63 or any(ord(char) < 32 for char in value)
                for value in (model, nickname)
            )
        ):
            return None
        recovery, web = data.get("inEmergRecovery"), data.get("hasWebIf")
        if type(recovery) is not bool or type(web) is not bool:
            return None
        return Device(
            mac,
            str(host),
            model,
            nickname,
            recovery,
            web,
            _supports_api(data.get("apiVer")),
        )
    except (KeyError, TypeError, ValueError, UnicodeError, RecursionError):
        return None


class _Receiver(asyncio.DatagramProtocol):
    """Collect valid responses without unbounded receive buffering."""

    def __init__(self) -> None:
        self.devices: dict[str, Device] = {}
        self.conflicts: set[str] = set()
        self.overflow = False
        self.error: OSError | None = None

    def datagram_received(self, data: bytes, addr: tuple[str, int]) -> None:
        device = parse_response(data, addr[0])
        if device is None:
            return
        previous = self.devices.get(device.mac)
        if previous is not None and previous.host != device.host:
            self.conflicts.add(device.mac)
        if previous is None and len(self.devices) >= MAX_DEVICES:
            self.overflow = True
            return
        self.devices[device.mac] = device

    def error_received(self, exc: Exception) -> None:
        self.error = OSError("ADAR socket failed")


def _sockets(interface: str) -> tuple[socket.socket, socket.socket]:
    """Receive multicast/broadcast on an ephemeral port and send from one interface."""
    listener = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sender = None
    try:
        sender = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        for sock in (listener, sender):
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.setblocking(False)
        listener.bind(("0.0.0.0", 0))
        listener.setsockopt(
            socket.IPPROTO_IP,
            socket.IP_ADD_MEMBERSHIP,
            socket.inet_aton(CLIENT_GROUP) + socket.inet_aton(interface),
        )
        sender.bind((interface, listener.getsockname()[1]))
        sender.setsockopt(
            socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(interface)
        )
        sender.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 255)
        sender.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        return listener, sender
    except BaseException:
        listener.close()
        if sender is not None:
            sender.close()
        raise


async def _scan_interface(interface: str, interval: float) -> DiscoveryResult:
    """Run bounded multicast rounds followed by limited-broadcast rounds."""
    sockets = _sockets(interface)
    transports: list[asyncio.DatagramTransport] = []
    receiver = _Receiver()
    complete = False
    try:
        loop = asyncio.get_running_loop()
        for sock in sockets:
            transport, _ = await loop.create_datagram_endpoint(
                lambda: receiver, sock=sock
            )
            transports.append(transport)
        broadcast = False
        for _ in range(6):
            previous = len(receiver.devices)
            transports[1].sendto(
                discovery_request(tuple(receiver.devices)),
                ("255.255.255.255" if broadcast else DEVICE_GROUP, DEVICE_PORT),
            )
            await asyncio.sleep(interval)
            if receiver.error is not None:
                raise receiver.error
            if receiver.overflow or len(receiver.devices) >= MAX_DEVICES:
                break
            if len(receiver.devices) == previous:
                if broadcast:
                    complete = True
                    break
                broadcast = True
        return DiscoveryResult(
            tuple(receiver.devices.values()), complete, frozenset(receiver.conflicts)
        )
    finally:
        for transport in transports:
            transport.close()
        for sock in sockets:
            sock.close()


async def discover(
    interfaces: tuple[str, ...], *, interval: float = 0.5
) -> DiscoveryResult:
    """Discover API-capable PixLite controllers on the supplied IPv4 interfaces."""
    if not 0 < interval <= 1:
        raise ValueError("Discovery interval must be between zero and one second")
    addresses = tuple(
        dict.fromkeys(str(IPv4Address(address)) for address in interfaces)
    )
    if not addresses:
        return DiscoveryResult(complete=False)
    results = await asyncio.gather(
        *(_scan_interface(address, interval) for address in addresses),
        return_exceptions=True,
    )
    devices: dict[str, Device] = {}
    conflicts: set[str] = set()
    complete = True
    for result in results:
        if isinstance(result, BaseException):
            if not isinstance(result, OSError):
                raise result
            complete = False
            continue
        complete &= result.complete
        conflicts.update(result.conflicts)
        for device in result.devices:
            previous = devices.get(device.mac)
            if previous is not None and previous.host != device.host:
                conflicts.add(device.mac)
            if previous is None and len(devices) >= MAX_DEVICES:
                complete = False
                continue
            devices[device.mac] = device
    return DiscoveryResult(
        tuple(
            sorted(
                (
                    device
                    for device in devices.values()
                    if device.eligible and device.mac not in conflicts
                ),
                key=lambda device: (device.nickname, device.host),
            )
        ),
        complete and not conflicts,
        frozenset(conflicts),
    )
