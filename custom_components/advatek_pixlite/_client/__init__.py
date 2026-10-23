"""Local PixLite API v1.9 HTTP client (no Home Assistant dependencies)."""

import asyncio
import base64
import hashlib
import re
from typing import Any

import aiohttp

from ._tls import (
    REQUEST_SECONDS,
    AdvatekTLS,
    CertificateError,
    InvalidMAC as InvalidMAC,
    normalize_mac,
)


class PixLiteError(Exception):
    """A transport, protocol or controller error."""

    def __init__(self, message: str, code: int | None = None) -> None:
        super().__init__(message)
        self.code = code


class InvalidAuth(PixLiteError):
    """Authentication failed."""


class InvalidCertificate(PixLiteError):
    """HTTPS certificate validation failed before an API exchange."""

    def __init__(self, verify_code: int | None = None) -> None:
        if verify_code in (2, 18, 19, 20, 21, 27):
            self.reason = "certificate_untrusted"
            message = "HTTPS certificate chain is not trusted. Obtain the Advatek root CA and configure trust in the Home Assistant runtime."
        elif verify_code in (62, 64):
            self.reason = "certificate_identity"
            message = "HTTPS certificate identity does not match the configured controller. Check the MAC address against its label."
        elif verify_code == 26:
            self.reason = "certificate_purpose"
            message = "HTTPS certificate is not valid for TLS server authentication. Contact Advatek."
        elif verify_code in (9, 10):
            self.reason = "certificate_validity"
            message = "HTTPS certificate is expired or not yet valid. Check the Home Assistant clock and contact Advatek."
        else:
            self.reason = "certificate_invalid"
            message = "HTTPS certificate validation failed. Contact Advatek for the correct certificate setup."
        super().__init__(message)


class UnsupportedDevice(PixLiteError):
    """Not a supported Mk3 API."""


def password_hash(password: str) -> str:
    return (
        base64.urlsafe_b64encode(hashlib.sha256(password.encode()).digest())
        .decode()
        .rstrip("=")
    )


def normalize_host(host: str) -> str:
    host = host.strip().lower()
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", host):
        raise ValueError("Enter an IPv4 address or hostname without a URL or port")
    return host


def _controller_identity(constants: dict[str, Any]) -> str:
    """Validate the controller MAC used by config entries and device identifiers."""
    dev = constants.get("dev")
    mac = dev.get("macAddr") if isinstance(dev, dict) else None
    if not isinstance(mac, str) or not re.fullmatch(
        r"(?:[0-9a-f]{12}|(?:[0-9a-f]{2}:){5}[0-9a-f]{2}|(?:[0-9a-f]{2}-){5}[0-9a-f]{2})",
        mac.lower(),
    ):
        raise PixLiteError("Invalid controller MAC address")
    identity = mac.replace("-", "").replace(":", "").lower()
    if identity == "000000000000" or int(identity[:2], 16) & 1:
        raise PixLiteError("Invalid controller MAC address")
    return identity


class PixLiteClient:
    def __init__(
        self,
        session: aiohttp.ClientSession,
        host: str,
        username: str = "admin",
        password: str = "",
        use_ssl: bool = False,
        port: int | None = None,
        expected_mac: str = "",
    ) -> None:
        self.session = session
        self.base_url = f"{'https' if use_ssl else 'http'}://{normalize_host(host)}:{port or (4443 if use_ssl else 80)}"
        self.auth = {"user": username, "auth": password_hash(password)}
        self.lock = asyncio.Lock()
        self.version: dict[str, Any] = {}
        self.constants: dict[str, Any] = {}
        self.expected_mac = normalize_mac(expected_mac) if expected_mac else ""
        self._tls = AdvatekTLS(normalize_host(host), port or 4443, self.expected_mac) if use_ssl and self.expected_mac else None

    async def _exchange(
        self, method: str, path: str, body: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        # One outstanding request per controller, including UI actions and polling.
        async with self.lock:
            try:
                async with asyncio.timeout(REQUEST_SECONDS):
                    fingerprint = await self._tls.fingerprint(self.session) if self._tls else None
                    async with self.session.request(
                        method,
                        self.base_url + path,
                        params=self.auth if method == "POST" else None,
                        json=body,
                        timeout=aiohttp.ClientTimeout(total=REQUEST_SECONDS),
                        headers={"Connection": "close"},
                        allow_redirects=False,
                        **({"ssl": fingerprint, "middlewares": ()} if self._tls else {}),
                    ) as response:
                        if response.status in (401, 403):
                            raise InvalidAuth("Controller rejected credentials")
                        if response.status != 200:
                            raise PixLiteError(
                                f"Controller returned HTTP {response.status}"
                            )
                        data = await response.json()
            except CertificateError as err:
                raise InvalidCertificate(err.verify_code) from None
            except aiohttp.ServerFingerprintMismatch:
                if self._tls:
                    self._tls.invalidate()
                raise InvalidCertificate() from None
            except aiohttp.ClientConnectorCertificateError as err:
                raise InvalidCertificate(
                    getattr(err.certificate_error, "verify_code", None)
                ) from None
            except aiohttp.ClientError, OSError, TimeoutError, ValueError:
                # Do not expose exception URLs: authentication is in the query string.
                raise PixLiteError("Unable to communicate with controller") from None
        if not isinstance(data, dict):
            raise PixLiteError("Invalid controller response")
        expected = body["req"] if body else "version"
        if data.get("resp") != expected:
            raise PixLiteError("Unexpected response type")
        if "err" in data:
            error = data["err"]
            code = error.get("code") if isinstance(error, dict) else None
            raise PixLiteError(f"Controller rejected {expected} (code {code})", code)
        result = data.get("result", {})
        if not isinstance(result, dict):
            raise PixLiteError("Invalid result object")
        return result

    async def request(
        self, name: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        body = {"req": name}  # req must be the first JSON member.
        if params is not None:
            body["params"] = params
        return await self._exchange("POST", "/v1.9/", body)

    async def read(
        self, object_name: str, paths: list[str] | None = None
    ) -> dict[str, Any]:
        result = await self.request(object_name + "Read", {"path": paths or [""]})
        value = result.get(object_name)
        if not isinstance(value, dict):
            raise PixLiteError(f"Missing {object_name} object")
        return value

    async def initialize(self) -> dict[str, Any]:
        self.version = await self._exchange("GET", "/ver")
        versions = self.version.get("apiVer", [])
        if not isinstance(versions, list) or any(
            not isinstance(version, dict)
            or not isinstance(version.get("maj"), str)
            or not isinstance(version.get("min"), list)
            or len(version["min"]) != 2
            or any(type(value) is not int or value < 0 for value in version["min"])
            or version["min"][0] > version["min"][1]
            for version in versions
        ):
            raise PixLiteError("Invalid API version response")
        if not any(
            v.get("maj") == "v1"
            and len(v.get("min", [])) == 2
            and v["min"][0] <= 9 <= v["min"][1]
            for v in versions
        ):
            raise UnsupportedDevice("Controller must support API v1.9")
        self.constants = await self.read("constant", ["dev", "ver"])
        dev = self.constants.get("dev", {})
        if not isinstance(dev, dict) or dev.get("prodFamilyName") != "PixLite Mk3":
            raise UnsupportedDevice("Expected a PixLite Mk3 with a MAC address")
        _controller_identity(self.constants)
        if self.expected_mac and self.unique_id != self.expected_mac:
            raise InvalidCertificate(62)
        return self.constants

    @property
    def unique_id(self) -> str:
        return _controller_identity(self.constants)

    async def verify_identity(self, expected_id: str) -> None:
        """Confirm the saved address still belongs to the configured controller."""
        constants = await self.read("constant", ["dev.macAddr"])
        if _controller_identity(constants) != expected_id:
            raise PixLiteError("A different controller is using this address; reconfigure the entry")

    async def files(self) -> list[str]:
        result = await self.request("fileList", {"pattern": ["*.scn", "*.pl"]})
        files = result.get("files")
        if not isinstance(files, list):
            raise PixLiteError("Missing file list")
        return sorted(
            {
                f["file"]
                for f in files
                if isinstance(f, dict)
                and isinstance(f.get("file"), str)
                and f["file"].lower().endswith((".scn", ".pl"))
            }
        )
