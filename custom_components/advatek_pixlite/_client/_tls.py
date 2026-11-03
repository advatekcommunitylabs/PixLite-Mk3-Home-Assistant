"""Authenticate the pinned Advatek certificate profile before sending HTTP."""

import asyncio
from datetime import UTC, datetime, timedelta
import hashlib
import ipaddress
import re
import ssl

import aiohttp
from cryptography import x509
from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID, ObjectIdentifier
from OpenSSL import crypto

from ._root import ROOT_PEM, ROOT_SHA256

REQUEST_SECONDS = 10
_NETSCAPE_TYPE = ObjectIdentifier("2.16.840.1.113730.1.1")
_SIGNATURES = {
    "1.2.840.113549.1.1.11",  # RSA with SHA-256
    "1.2.840.113549.1.1.12",  # RSA with SHA-384
    "1.2.840.113549.1.1.13",  # RSA with SHA-512
    "1.2.840.10045.4.3.2",  # ECDSA with SHA-256
    "1.2.840.10045.4.3.3",  # ECDSA with SHA-384
    "1.2.840.10045.4.3.4",  # ECDSA with SHA-512
}


class CertificateError(Exception):
    """A fixed diagnostic code with no peer-controlled text."""

    def __init__(self, verify_code: int | None = None):
        self.verify_code = verify_code


class InvalidMAC(ValueError):
    """The configured identity is not a unicast controller MAC."""


def normalize_mac(value: str) -> str:
    """Accept a printed unicast MAC, with optional byte separators."""
    if not isinstance(value, str) or not re.fullmatch(
        r"(?:[0-9a-fA-F]{12}|(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}|(?:[0-9a-fA-F]{2}-){5}[0-9a-fA-F]{2})",
        value,
    ):
        raise InvalidMAC("Invalid controller MAC address")
    mac = value.replace(":", "").replace("-", "").lower()
    if mac == "000000000000" or int(mac[:2], 16) & 1:
        raise InvalidMAC("Invalid controller MAC address")
    return mac


def _extension(cert: x509.Certificate, kind):
    try:
        return cert.extensions.get_extension_for_class(kind).value
    except x509.ExtensionNotFound:
        return None


def _validate_chain(
    chain: tuple[bytes, ...], mac: str, valid_through: datetime,
) -> bytes:
    """Return a leaf digest only after strict path and vendor-profile checks."""
    try:
        if not 2 <= len(chain) <= 3 or any(not 0 < len(c) <= 16384 for c in chain):
            raise CertificateError()
        if len(set(chain)) != len(chain):
            raise CertificateError()
        certificates = [x509.load_der_x509_certificate(c) for c in chain]
        root = x509.load_pem_x509_certificate(ROOT_PEM)
        root_der = root.public_bytes(serialization.Encoding.DER)
        if root.fingerprint(hashes.SHA256()).hex() != ROOT_SHA256:
            raise CertificateError(20)
        if len(chain) == 3 and chain[2] != root_der:
            raise CertificateError(20)

        store = crypto.X509Store()
        store.add_cert(crypto.X509.from_cryptography(root))
        store.set_flags(
            crypto.X509StoreFlags.X509_STRICT
            | crypto.X509StoreFlags.CHECK_SS_SIGNATURE
            | crypto.X509StoreFlags.POLICY_CHECK
        )
        context = crypto.X509StoreContext(
            store, crypto.X509.from_cryptography(certificates[0]),
            [crypto.X509.from_cryptography(certificates[1])],
        )
        accepted = [cert.to_cryptography() for cert in context.get_verified_chain()]
        expected = [chain[0], chain[1], root_der]
        if [c.public_bytes(serialization.Encoding.DER) for c in accepted] != expected:
            raise CertificateError(20)

        now = datetime.now(UTC)
        for cert in accepted:
            if cert.not_valid_before_utc > now or cert.not_valid_after_utc <= valid_through:
                raise CertificateError(10)
            period = _extension(cert, x509.PrivateKeyUsagePeriod)
            if period is not None:
                before = period.not_before.replace(tzinfo=UTC) if period.not_before else None
                after = period.not_after.replace(tzinfo=UTC) if period.not_after else None
                if (before and before > now) or (after and after <= valid_through):
                    raise CertificateError(10)
            if any(ext.oid == _NETSCAPE_TYPE for ext in cert.extensions):
                raise CertificateError(26)
            key = cert.public_key()
            strong = (
                isinstance(key, rsa.RSAPublicKey)
                and 2048 <= key.key_size <= 4096
                and key.public_numbers().e == 65537
            ) or (
                isinstance(key, ec.EllipticCurvePublicKey)
                and isinstance(key.curve, (ec.SECP256R1, ec.SECP384R1))
            )
            if not strong or cert.signature_algorithm_oid.dotted_string not in _SIGNATURES:
                raise CertificateError()

        leaf = accepted[0]
        subject = list(leaf.subject)
        if len(subject) != 1 or subject[0].oid != NameOID.COMMON_NAME:
            raise CertificateError(62)
        cn = subject[0].value
        if not re.fullmatch(r"[0-9a-fA-F]{12}", cn) or cn.lower() != mac:
            raise CertificateError(62)
        constraints = _extension(leaf, x509.BasicConstraints)
        eku = _extension(leaf, x509.ExtendedKeyUsage)
        if (
            constraints is None or constraints.ca
            or eku is None or list(eku) != [ExtendedKeyUsageOID.ANY_EXTENDED_KEY_USAGE]
            or _extension(leaf, x509.KeyUsage) is not None
            or _extension(leaf, x509.SubjectAlternativeName) is not None
        ):
            raise CertificateError(26)
        for cert in accepted[1:]:
            constraints = _extension(cert, x509.BasicConstraints)
            usage = _extension(cert, x509.KeyUsage)
            eku = _extension(cert, x509.ExtendedKeyUsage)
            if (
                constraints is None or not constraints.ca
                or usage is None or not usage.key_cert_sign
                or (eku is not None and (
                    not eku or any(oid not in (
                        ExtendedKeyUsageOID.ANY_EXTENDED_KEY_USAGE,
                        ExtendedKeyUsageOID.SERVER_AUTH,
                    ) for oid in eku)
                ))
            ):
                raise CertificateError(26)
        return hashlib.sha256(chain[0]).digest()
    except crypto.X509StoreContextError as err:
        code = err.errors[0] if err.errors else None
        raise CertificateError(code) from None
    except (
        ValueError, TypeError, UnsupportedAlgorithm, crypto.Error,
        x509.DuplicateExtension, x509.UnsupportedGeneralNameType,
    ):
        raise CertificateError() from None


async def _capture_chain(host: str, port: int) -> tuple[bytes, ...]:
    """Capture certificates over TLS without sending any application bytes."""
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.set_alpn_protocols(["http/1.1"])
    writer = None
    try:
        _, writer = await asyncio.open_connection(
            host, port, ssl=context, server_hostname=host,
            ssl_handshake_timeout=REQUEST_SECONDS, ssl_shutdown_timeout=1,
        )
        peer = writer.get_extra_info("ssl_object")
        if peer is None or peer.session_reused or peer.selected_alpn_protocol() not in (None, "http/1.1"):
            raise CertificateError()
        chain = tuple(peer.get_unverified_chain())
        if not 2 <= len(chain) <= 3 or any(not 0 < len(c) <= 16384 for c in chain):
            raise CertificateError()
        return chain
    finally:
        if writer is not None:
            writer.close()
            try:
                async with asyncio.timeout(1):
                    await writer.wait_closed()
            except (OSError, TimeoutError):
                pass
            finally:
                writer.transport.abort()


class AdvatekTLS:
    """Per-controller certificate cache, authenticated again before every request."""

    def __init__(self, host: str, port: int, expected_mac: str):
        # A literal address avoids resolving to multiple peers within one request.
        self.host = str(ipaddress.IPv4Address(host))
        self.port = port
        self.mac = normalize_mac(expected_mac)
        self._chain: tuple[bytes, ...] | None = None

    async def fingerprint(self, session: aiohttp.ClientSession) -> aiohttp.Fingerprint:
        """Validate immutable bytes in a worker before publishing the cache."""
        if session.trust_env or session.auth is not None:
            raise CertificateError()
        chain = self._chain
        if chain is None:
            chain = await _capture_chain(self.host, self.port)
        try:
            digest = await asyncio.to_thread(
                _validate_chain, chain, self.mac,
                datetime.now(UTC) + timedelta(seconds=REQUEST_SECONDS + 1),
            )
        except CertificateError:
            self.invalidate()
            raise
        self._chain = chain
        return aiohttp.Fingerprint(digest)

    def invalidate(self) -> None:
        """Require a new certificate capture on the next independent request."""
        self._chain = None
