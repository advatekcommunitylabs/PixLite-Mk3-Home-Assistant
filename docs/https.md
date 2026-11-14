# Advatek HTTPS verification

Advatek Lighting's PixLite Mk3 API v1.9, document V20260617 (17 June 2026), section 4.1 specifies HTTPS port 4443 and an Advatek root CA available from Advatek. It does not specify a MAC-CN identity policy or the certificate-purpose exception implemented here. This profile is deliberately limited to the certificate structure observed on the A4-S and E16-S firmware 3.15.0 units and independently reviewed against captured certificates. It is not a claim that Advatek has documented this policy for every firmware or model.

## Trust and identity

The public root in `_client/_root.py` was extracted from the official [Advatek Assistant 3 v1.1.4 installer](https://assistant.advateklighting.com/releases/Advatek%20Assistant%203%20Setup%201.1.4.exe). The installer had a Valid Windows Authenticode signature for Advatek Lighting Pty Ltd, independently checked during this review. No Assistant executable or proprietary implementation is included.

- Installer SHA-256: `3243262fe031d65121f09fd459aaf27b9d515f4e52be4192879885c339f14752`
- Authenticode signer thumbprint: `F738505AE2B73D697BAEF3DC805C266AB35E863C`
- Root DER SHA-256: `221b86c50a93c056979c28e7822fd30c58c01e48b7a34b5f8c4ab78d58510344`
- Root subject: `Advatek Lighting Device Root CA 1`

The user supplies a MAC independently from the controller label. The leaf must contain exactly one subject attribute, a 12-hex-digit MAC Common Name matching that identity. MAC letter case is ignored. SANs, additional subject attributes and duplicate CNs are rejected. No identity or root is learned from the peer, discovery reply, first successful API response or system trust store.

With the Advatek profile enabled, an untrusted-chain error concerns the embedded root and required path. Changing Home Assistant's system CA store cannot override this check. With MAC left blank, the conventional CA trust diagnostic applies instead.

## Certificate and connection checks

A separate TLS connection captures certificates without sending HTTP, credentials or other application bytes. A fresh private capture context negotiates TLS 1.2 or later and HTTP/1.1; it performs no CA/hostname authentication itself. The captured bytes are subsequently authenticated in memory by a worker using a store containing only the pinned root.

The completed OpenSSL path must be exactly the supplied leaf, one supplied issuing CA and the embedded root. The wire chain can omit the root or include that exact root. Duplicate, missing, extra, substituted, oversized and malformed certificates fail. Strict X.509, policy checking and root self-signature checking remain enabled. Unknown critical extensions, CA constraints and policy constraints are checked by the path validator.

The leaf requires CA=false, exactly Any Extended Key Usage, no Key Usage and no SAN. Every CA requires CA=true and certificate-signing Key Usage. A CA EKU, if present, may contain only Any or server authentication. Netscape Certificate Type is forbidden throughout the path. Keys are restricted to RSA 2048 through 4096 bits with exponent 65537, or P-256/P-384 EC. Signatures are restricted to RSA PKCS#1 or ECDSA with SHA-256/384/512. Certificate validity and any Private Key Usage Period bounds must cover the complete remaining bounded request, with a margin.

Each API connection uses a new public `aiohttp.Fingerprint` for the validated leaf's SHA-256 digest. This verifies that the actual TLS peer presents the accepted leaf and proves possession of its key before HTTP is sent. Per-request pin objects and `Connection: close` isolate connections. All requests are HTTPS, redirects are disabled, and a literal IPv4 address prevents retrying a list of DNS targets. aiohttp may retry an idempotent GET following a disconnect; dispatched operator POSTs are never replayed. No failed operation falls back to HTTP or automatically retries with a newly captured certificate.

Captured certificate bytes are cached per client and revalidated before every request. A failed cached validation or actual leaf mismatch clears that cache, fails the current operation, and permits capture only on a later independent request. A ten-second total deadline covers capture, validation and the API exchange. Cancellation cannot publish a late worker result or initiate late HTTP. Nothing is written to temporary certificate files and no external verifier process is launched. See the [caller session contract](client.md).

## Limits and validation

CRL and OCSP revocation are not fetched or claimed. The clock, installed package source, embedded root and caller-owned session are trusted infrastructure. A compromised device private key or a compromised Advatek CA requires an out-of-band response. Unrecognized future certificate profiles fail closed and require a reviewed update.

The [Windows cleanup investigation](windows-cleanup.md) confirms an upstream CPython failure mechanism that can interrupt socket cleanup after a reset. CPython merged a maintained correction on 5 November 2026, but this project has not qualified a released runtime containing it. The original affected socket remains unidentified. The beta does not include the private test patch, and loopback results do not establish Windows endurance or Linux qualification.

The synthetic tests exercise valid paired controllers, complete path validation, malformed and restricted certificate cases, pre-HTTP rejection, leaf substitution, cached expiry and renewal, cancellation and timeout, independent clients, connection isolation, redirects and lost operator responses. The conventional CA/hostname TLS tests remain separate. Real HA setup/reconfiguration, all seven custom platforms and reload/unload isolation are also exercised against two local TLS simulators. Live A4/E16 results are recorded in [the device audit](per-device-audit.md), separately from simulator evidence. Windows tests do not qualify Linux contribution tests, upstream acceptance or emitted-light behavior.

The implementation uses the public [pyOpenSSL X509Store API](https://www.pyopenssl.org/en/stable/api/crypto.html), [OpenSSL verification flags](https://docs.openssl.org/3.5/man1/openssl-verification-options/) and [aiohttp fingerprint API](https://docs.aiohttp.org/en/stable/client_advanced.html#example-verify-certificate-fingerprint). The vendor usage policy above supplies the purpose restrictions that ordinary server-purpose validation cannot provide for these observed certificates.
