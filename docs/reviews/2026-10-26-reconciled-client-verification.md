# Reconciled client verification, 26 October 2026

This implementation and review are fully AI-generated. A separate AI reviewer inspected the candidate and evidence without executing tests. Human review remains required. Only reviewed and verified features should be added or merged. PR #2 remains draft.

## Change

The candidate combines PR #2 at `70d4d81b21172dc4dd1fbfce64ab843589ffca49` with the remaining client validation reviewed in Sam's PR #1 at `09fea8cbb74bc854e4b8e6b8e724f060ae383988` (code revision `211b4580d525552b060044e0866aa38b45b3b513`).

Controller error envelopes require an object with an integer code, excluding booleans. Malformed codes produce a fixed error without reflecting arbitrary response data. Initialization rejects missing API-version metadata, invalid nicknames, empty or invalid product names and invalid firmware objects. Constants become available only after validation and expected-MAC matching. The existing HTTPS, colour, runtime identity, explicit port clearing and media-list cadence behavior is retained.

## Offline verification

On Windows, CPython 3.14.2 and actual Home Assistant 2026.10.2, 307 tests passed with 56 visible warnings. Coverage includes the protocol client, controls, colour/file labels, two actual HA simulator entries, lifecycle/configuration flows and both conventional and Advatek TLS security. Two tightened missing-field cases subsequently passed; no production code changed after the 307-test run. Ruff passed all five changed source/test files.

The physical harness separately passed 28 handover/lease cases, two real loopback TLS closure checks and two unsuccessful-report checks for cleanup failures. These offline results do not establish physical device behavior. The separate AI reviewer found no remaining source or admission blocker on the frozen versions.

## Paired physical verification

After fresh coordinator allocation, the frozen candidate ran from 18:51:57.649635 to 18:53:01.950037 UTC on 26 October, lasting 64.3 seconds. Both A4-S (RGBWX) and E16-S (RGB), firmware 3.15.0, passed authenticated Advatek HTTPS on port 4443 with full pinned-root path validation and provisioned MAC verification before application data.

Both actual HA entries loaded all seven platforms, completed native entity-enable reloads and three paired polling cycles, and passed reload/unload isolation. There were 107 logical client invocations: 105 without recorded client errors and two deliberate wrong-MAC certificate rejections. These are attempted logical exchanges, not an independent packet capture. Only version, constant, configuration, status, statistics and file-list reads were allowed; no operating, configuration or media writes were sent.

Fresh before/after comparisons preserved operating mode and parameters, both intensity factors and priority, Identify, full configuration and catalogue metadata for both devices. Raw configuration and catalogue responses were retained privately, allowing independent recalculation of the matching hashes. Media file contents were not read or verified.

All 116 tracked HA-owned TLS transports (60 A4, 56 E16) had closed sockets, cleared socket references and completed cleanup while strong references remained held. No loop error, callback exception or Windows reset-cleanup warning was recorded. Ordinary HA custom-integration and optional-compression warnings remain visible. The supervisor exited zero without forced termination, and a fresh process inventory found no owned runtime, supervisor or observed descendants. HA explicitly released its allocation after verification.

## Source and runtime identity

- Tested Windows integration/dependency digest: `91cb4366fc4dd48a89302bc905d82f7f862b450fe5bbfe3783b579731a825e13` (22 source hashes independently matched).
- Git LF integration/dependency digest: `e7075172e0b25f9214e29007151d6eb216e8d8438b782b634da6aa7a3fed121d`. Every staged production/dependency file and changed test file equals the tested file after Git's CRLF-to-LF normalization; no other byte changes were accepted.
- Physical harness SHA-256: `72772c57c7ce604007e1ca687f9124a7f6e5c6965da0946f26acd37e6d11eafe`.
- Supervisor SHA-256: `2b3a96d3c929b21b24d561b8066997137757edec6a7a0e61e00b250096126866`.
- Isolated `proactor_events.py` SHA-256: `1180abffc010ce51d0188e9b0419d113e38cac76545bdf95e14ee1fd07797469`.
- Physical report SHA-256: `6fcdb32745681df45d26815612ffebc54763b18876ccb5f9cefcd3bb2af93248`.

The runtime correction was loaded only in the private child process. Installed Python remained unchanged. It is not installed, bundled with the integration or accepted upstream.

## Limits

This read-only run does not repeat operating controls or emitted-light validation, reproduce the original reset timing, identify its original socket, or qualify endurance, other firmware/models, physical RGBW installations or Linux. It used no synthetic reset injection against hardware. User browser tabs were untouched; global TCP quiet is not claimed. No files were deleted and no CI was dispatched for this follow-up.

The [Windows cleanup deployment gate](../windows-cleanup.md) remains open. Earlier operating-control evidence in the [per-device audit](../per-device-audit.md) belongs to its recorded source revision. Final merged/rebased source, supported runtime deployment, target Core checks, dependency release and human review remain separate release requirements.
