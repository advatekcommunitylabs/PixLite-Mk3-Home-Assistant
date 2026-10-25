# Windows cleanup investigation

23 October 2026. This investigation used CPython 3.14.2, aiohttp 3.14.5, pyOpenSSL 26.4.0 and cryptography 50.0.1 on Windows. It made no controller requests. Linux checks were cancelled at the user's instruction and remain unverified. PR #2 must remain a draft.

## Confirmed cleanup defect

The earlier paired hardware run logged `WinError 10054` from CPython's `_ProactorBasePipeTransport._call_connection_lost()`. That callback invokes `socket.shutdown()` before closing the socket, detaching its server and marking cleanup complete. A shutdown exception escapes before those later operations.

A standalone fault-injection diagnostic called the **unmodified installed callback** with a wrapper owning a real socket. The normal control case closed the socket and completed cleanup. Five injected shutdown resets each produced the callback exception, left the socket open and skipped the completion flag. The diagnostic's own `finally` then closed every socket. This confirms the cleanup failure mechanism; it does not reproduce the original TCP timing or identify which socket produced the hardware-run warning.

The installed callback and the official CPython 3.14 branch had identical abstract syntax when checked. The inspected source is pinned to [CPython commit 60067a6, 12 October 2026](https://github.com/python/cpython/blob/60067a6bbad9f5556106a807f7102b6a797129a2/Lib/asyncio/proactor_events.py). The exact defect is also tracked in [CPython issue #160429, opened by h3har on 23 October 2026](https://github.com/python/cpython/issues/160429). That issue remained open when checked; no verified runtime fix is claimed here.

Possible socket retention until finalization remains a real concern. The observation does not establish a TLS authentication failure, an unacknowledged operating write, or a failed restoration. The earlier log does not identify whether certificate capture, aiohttp or another socket owned the failing transport.

## Loopback evidence and limits

The unchanged client was exercised against synthetic TLS peers on `127.0.0.1`:

| Path | Cycles | TLS connections | HTTP requests |
| --- | ---: | ---: | ---: |
| Certificate capture only | 160 | 160 | 0 |
| Validated-leaf API connection | 160 | 160 | 160 |
| Capture followed by API connection | 160 | 320 | 160 |

Each path covered ordinary peer closure and forced resets after delays of zero, one and ten milliseconds. Across 480 cycles and 640 TLS connections, the callback warning did not recur and the recorded process-handle counts showed no upward trend. These samples are not an endurance or leak-free qualification.

Immediate resets produced nine expected client communication errors (three API-only and six combined-path cases). The server still recorded exactly one HTTP request per API operation, demonstrating no POST replay. Delayed-reset and ordinary-close cases completed without client errors. A separate five-case raw TCP-reset experiment also failed to reproduce the callback warning. Its unsuccessful reproduction assertion and evidence were retained.

## Review gate

This is a confirmed upstream cleanup failure mechanism with an unresolved runtime fix and unidentified original socket. No production transport code, interpreter installation or event-loop policy was changed. Diagnostic exception handlers forwarded exceptions to the default handler; warnings were not suppressed. Existing files and investigation artifacts were preserved.

Keep the Windows finding open until a reviewed runtime or integration change is verified against deterministic cleanup assertions and reset/cancellation tests. Changing the integration merely to hide the callback would not prove resource cleanup. Preserve the existing certificate, identity and no-replay guarantees. Supported Linux and endurance qualification remain unperformed; this investigation does not clear release or merge readiness.

## Isolated runtime candidate, 25 October 2026

A local CPython 3.14.2 candidate puts socket closure, server detachment and completion marking in a `finally` after shutdown. It handles only `ConnectionResetError` with Windows error 10054 as an expected peer reset, retaining debug logging. Unexpected shutdown and protocol errors still propagate after cleanup. Failures in socket `close()` or server `_detach()` remain outside this narrow correction. The candidate was loaded through a child-only `PYTHONPATH`; the installed interpreter, integration TLS implementation and global event-loop policy were not modified.

Offline verification passed four unit-test methods, including 15 error combinations, 30 real Proactor transport cases and all 76 existing integration TLS/security tests. In the accepted fault-injected loopback comparison, the original callback left 32 tracked sockets open after 32 shutdown resets. The candidate closed all 160 tracked TLS sockets after 160 resets. Eight communication failures under deliberate immediate peer resets remained recorded separately; they were not described as successful API operations. An independent AI reviewer inspected the patch and evidence without executing tests. The native CPython regression suite and other Python versions were not run.

After a fresh coordinator allocation and restoration handover, the isolated candidate also passed a read-only physical run on both A4-S and E16-S controllers, from 16:25:05 to 16:26:07 UTC on 25 October. The 62.7-second main run completed 107 logical client invocations, including two deliberate wrong-MAC rejections, with no other client errors. Actual HA entries loaded all seven platforms, completed native entity-enable reloads and three paired polling cycles, and passed reload/unload isolation. Both fresh baselines were preserved: A4 red Color at 8-bit resolution and E16 Live, including operating parameters, programmed factors/priorities, Identify, full configuration and scene/playlist metadata hashes. No operating, configuration or media writes were sent.

The test observed 116 HA-owned real TLS transports (60 A4, 56 E16). After HA stopped, every tracked socket descriptor was closed, its transport socket reference was cleared and its cleanup completion flag was set. Strong references remained held, so garbage collection could not conceal incomplete deterministic cleanup. No callback exception or Windows reset-cleanup warning occurred. The external supervisor exited normally without forcing termination; all owned processes and observed descendants were absent before explicit release. User device SPAs remained open and untouched, so global TCP quiet was not claimed.

This physical run used no synthetic reset injection. It verifies observed cleanup under the candidate on both devices; it does not reproduce the original reset timing, identify its original socket, qualify endurance or verify raw media contents. The tested candidate `proactor_events.py` SHA-256 is `1180abffc010ce51d0188e9b0419d113e38cac76545bdf95e14ee1fd07797469`; the integration source digest remains `aa87cbc5971e7fb07a502bb162a8c5f33a99b1a5dd308310491d496c5e9986f1`.

The candidate is not installed, bundled with the integration or submitted upstream. Supported runtime deployment remains open. PR #2 stays draft, GitHub Actions stays disabled, and Linux checks remain cancelled. No files were deleted during this follow-up.
