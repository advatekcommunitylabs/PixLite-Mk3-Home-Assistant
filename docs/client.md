# PixLite client library

The `advatek-pixlite-client` distribution contains the asynchronous HTTP protocol client without a Home Assistant dependency. Its canonical source is `custom_components/advatek_pixlite/_client`; the custom integration's `api.py` reexports that client so a manual custom integration installation remains self-contained. Core uses the separately installed `advatek_pixlite_client` package instead.

Build a wheel and source distribution from the repository root with `python -m build`. For development, install it with `python -m pip install -e .`.

Version 0.1.0 is a proposed first release, not an existing PyPI release. Do not publish it or add it to an upstream requirement until the source, release contents and license have been reviewed. Publication requires an agreed OSI-approved license, a public source repository and issue tracker, a matching release tag, and a public CI build and publication workflow. No license grant or release approval is asserted by this preparation.

The library uses a caller-owned aiohttp session, serializes HTTP requests, checks API v1.9 support, authenticates with the controller's password-hash query format, and returns controller objects. It does not configure Home Assistant, install entities, or manage Home Assistant state.

`InvalidCertificate` is a `PixLiteError` subclass for failed HTTPS certificate verification. Its `reason` identifies a fixed trust, identity, purpose, validity or generic certificate error without exposing peer-controlled certificate text or credential-bearing URLs. It does not modify the caller's TLS policy or retry over HTTP.

For the Advatek certificate profile, set `use_ssl=True` and `expected_mac` to the MAC independently obtained from the controller label. This path requires a literal IPv4 address. With no expected MAC, HTTPS retains the caller's conventional CA and hostname policy. Existing entries do not silently opt in. See [HTTPS verification](https.md) for the supported profile and authenticated root provenance.

The caller-owned session must be trusted application infrastructure: no explicit or environment proxy, proxy credentials, default authentication, credential-bearing default headers, request-mutating trace callbacks or custom connector behavior that bypasses TLS/fingerprint checks. Home Assistant's normal `async_get_clientsession(hass)` satisfies this contract. The vendor path rejects `trust_env` and default authentication through public session APIs; aiohttp exposes no public getter for an explicitly configured session proxy, so that remains a caller obligation. Per-request middleware is disabled and redirects are forbidden. Do not pass sessions sourced from untrusted plugins or a user-defined transport.

The vendor path uses pyOpenSSL 26.4.x and its declared cryptography dependency for in-memory X.509 path validation, and aiohttp 3.14.5 or later in the 3.x series for public fingerprint verification. `OpenSSL.crypto` has pending deprecation in the upstream documentation. Requalify the chain constraints, pre-HTTP pinning and cancellation tests before changing either dependency range; replacing path validation with individual signature checks is insufficient.
