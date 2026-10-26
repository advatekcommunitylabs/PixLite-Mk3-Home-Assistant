"""Local PixLite API v1.9 HTTP client (no Home Assistant dependencies)."""
import asyncio
import base64
import hashlib
import re

import aiohttp


class PixLiteError(Exception):
    """A transport, protocol or controller error."""

    def __init__(self, message, code=None):
        super().__init__(message)
        self.code = code


class InvalidAuth(PixLiteError):
    """Authentication failed."""


class UnsupportedDevice(PixLiteError):
    """Not a supported Mk3 API."""


class IdentityMismatch(PixLiteError):
    """The configured address now belongs to a different controller."""


def normalize_mac(value):
    """Validate identity before using it in HA's persistent registries."""
    if not isinstance(value, str) or not re.fullmatch(
        r"(?:[0-9a-fA-F]{12}|[0-9a-fA-F]{2}(?:-[0-9a-fA-F]{2}){5}|[0-9a-fA-F]{2}(?::[0-9a-fA-F]{2}){5})", value
    ):
        raise PixLiteError("Invalid controller MAC address")
    mac = value.replace("-", "").replace(":", "").lower()
    if mac in ("000000000000", "ffffffffffff"):
        raise PixLiteError("Invalid controller MAC address")
    return mac


def password_hash(password):
    return base64.urlsafe_b64encode(hashlib.sha256(password.encode()).digest()).decode().rstrip("=")


def normalize_host(host):
    host = host.strip().lower()
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?", host):
        raise ValueError("Enter an IPv4 address or hostname without a URL or port")
    return host


class PixLiteClient:
    def __init__(self, session, host, username="admin", password="", use_ssl=False, port=None):
        self.session = session
        self.base_url = f"{'https' if use_ssl else 'http'}://{normalize_host(host)}:{port or (4443 if use_ssl else 80)}"
        self.auth = {"user": username, "auth": password_hash(password)}
        self.lock = asyncio.Lock()
        self.version = {}
        self.constants = {}

    async def _exchange(self, method, path, body=None):
        # One outstanding request per controller, including UI actions and polling.
        async with self.lock:
            try:
                async with self.session.request(
                    method, self.base_url + path,
                    params=self.auth if method == "POST" else None,
                    json=body, timeout=aiohttp.ClientTimeout(total=10),
                    headers={"Connection": "close"}, allow_redirects=False,
                ) as response:
                    if response.status in (401, 403):
                        raise InvalidAuth("Controller rejected credentials")
                    if response.status != 200:
                        raise PixLiteError(f"Controller returned HTTP {response.status}")
                    data = await response.json()
            except (aiohttp.ClientError, TimeoutError, ValueError):
                # Do not expose exception URLs: authentication is in the query string.
                raise PixLiteError("Unable to communicate with controller") from None
        if not isinstance(data, dict):
            raise PixLiteError("Invalid controller response")
        expected = body["req"] if body else "version"
        if data.get("resp") != expected:
            raise PixLiteError("Unexpected response type")
        if "err" in data:
            error = data["err"]
            if not isinstance(error, dict) or type(error.get("code")) is not int:
                # Never reflect arbitrary response JSON: it can contain credentials.
                raise PixLiteError("Invalid controller error response")
            code = error["code"]
            raise PixLiteError(f"Controller rejected {expected} (code {code})", code)
        result = data.get("result", {})
        if not isinstance(result, dict):
            raise PixLiteError("Invalid result object")
        return result

    async def request(self, name, params=None):
        body = {"req": name}  # req must be the first JSON member.
        if params is not None:
            body["params"] = params
        return await self._exchange("POST", "/v1.9/", body)

    async def read(self, object_name, paths=None):
        result = await self.request(object_name + "Read", {"path": paths or [""]})
        value = result.get(object_name)
        if not isinstance(value, dict):
            raise PixLiteError(f"Missing {object_name} object")
        return value

    async def initialize(self):
        self.version = await self._exchange("GET", "/ver")
        versions = self.version.get("apiVer")
        if not isinstance(versions, list):
            raise PixLiteError("Invalid API version list")
        if "nickname" in self.version and not isinstance(self.version["nickname"], str):
            raise PixLiteError("Invalid controller nickname")
        for version in versions:
            if not isinstance(version, dict) or not isinstance(version.get("maj"), str):
                raise PixLiteError("Invalid API version entry")
            limits = version.get("min")
            if (not isinstance(limits, list) or len(limits) != 2
                    or any(type(value) is not int or value < 0 for value in limits)
                    or limits[0] > limits[1]):
                raise PixLiteError("Invalid API version range")
        if not any(v["maj"] == "v1" and v["min"][0] <= 9 <= v["min"][1] for v in versions):
            raise UnsupportedDevice("Controller must support API v1.9")
        constants = await self.read("constant", ["dev", "ver"])
        dev = constants.get("dev")
        if not isinstance(dev, dict):
            raise PixLiteError("Invalid controller device object")
        normalize_mac(dev.get("macAddr"))
        if dev.get("prodFamilyName") != "PixLite Mk3":
            raise UnsupportedDevice("Expected a PixLite Mk3 with a MAC address")
        if not isinstance(dev.get("prodName"), str) or not dev["prodName"].strip():
            raise PixLiteError("Invalid controller product name")
        if "ver" in constants and not isinstance(constants["ver"], dict):
            raise PixLiteError("Invalid controller firmware object")
        self.constants = constants
        return self.constants

    @property
    def unique_id(self):
        return normalize_mac(self.constants.get("dev", {}).get("macAddr"))

    async def verify_identity(self, expected_id):
        """Detect address reuse; this is not cryptographic authentication."""
        constants = await self.read("constant", ["dev.macAddr"])
        dev = constants.get("dev")
        if not isinstance(dev, dict):
            raise PixLiteError("Invalid controller device object")
        if normalize_mac(dev.get("macAddr")) != expected_id:
            raise IdentityMismatch("Controller identity mismatch at configured address; reconfigure the original controller or add the replacement separately")

    async def files(self):
        result = await self.request("fileList", {"pattern": ["*.scn", "*.pl"]})
        files = result.get("files")
        if not isinstance(files, list):
            raise PixLiteError("Missing file list")
        return sorted({f["file"] for f in files if isinstance(f, dict)
                       and isinstance(f.get("file"), str)
                       and f["file"].lower().endswith((".scn", ".pl"))})
