# Per-device integration audit

23 October 2026. This is a fully AI-generated implementation and review. A separate AI reviewer audited the source read-only, reproduced findings, and reviewed the fixes. This is not a human audit or third-party certification. Only reviewed and verified features should be added or merged.

## Findings and changes

| Finding | Change | Verification |
| --- | --- | --- |
| P1: A reused address could control another controller after setup | Check the saved MAC through authenticated API reads before every polling cycle and every output request, including requests within one action | Substitute a simulator's MAC after setup and between writes; reject output, mark only that entry unavailable, preserve peer polling |
| P2: Positive brightness leaves Blank or a black solid colour off | Build the complete On action from fresh configuration and status under the controller lock; restore a visible colour only for positive brightness | Actual HA light services for RGB, RGBW and RGBWX; preserve File/Live modes; zero brightness does not restore colour |
| P2: Consecutive services return stale state | Await immediate refresh outside the command lock after success or failure; manual file refresh also bypasses debounce | Repeated service calls through the real coordinator and HTTP transport; partial failures reconcile without repeating writes |
| P2: Clearing a custom port preserves the previous port | Save an explicit default-port value and omit a null schema default | Saved entry check, followed by reconfigure and reauthentication form validation |
| P2: Malformed version or identity data escapes normal error handling | Validate version structures and nonzero unicast MAC addresses in the protocol client | Malformed HTTP payload tests; staged Core monitoring coordinator also uses the validated identity boundary |
| P3: Handled file-list errors cause excessive retries | Advance the attempt timestamp for errors 10 and 14 | Consecutive polls make one file-list request; explicit file refresh still retrieves new files immediately |
| P2: The Core export omitted the sensor filename helper | Export `file_names.py` alongside the sensor platform | Generate a fresh tree, import the exported sensor platform and check supported sensors and extensionless values |

Shared identity, configuration, protocol and file-refresh fixes are also backported to the separate ADAR PR #3. The colour restoration change belongs to PR #2. PR #3 alone retains its older colour implementation and must not be treated as the combined feature release.

## Original safety-audit verification

Python 3.14.2 and Home Assistant 2026.10.2 on Windows. All checks were local; GitHub Actions remains disabled.

- Feature suite: **172 tests passed**, including three staged Core identity checks and an exported sensor-platform smoke check. The custom integration has **96% statement coverage (693/725 statements)**. Coverage used Python tracing because the default Python 3.14 monitoring collector omitted executed client/button code. Branch coverage was not measured.
- Separate ADAR branch: **225 tests passed**, including real HA configuration flows, registries, services and two in-process HTTP controllers.
- Combined local candidate: **168 custom integration tests passed**, using feature code with ADAR setup/discovery overlaid. This is compatibility evidence, not a merged release artifact.
- The independent AI reviewer separately ran **71 API/device-runtime tests**, after correcting a port-form regression discovered during re-review. Remaining tests were run by the implementation agent.
- Ruff checks and whitespace checks passed for the changed code. Existing dependency warnings remain. The Linux upstream Home Assistant suite and complete Core checks were not run in this audit.

| Per-device area | Verified behaviour |
| --- | --- |
| All seven entity platforms | Distinct device/entry/entity identities even with duplicate nicknames; commands target the selected controller |
| Sensors and binary sensors | Capability-specific A4 power measurements, E16 exclusions, separate health/playback state and failure availability |
| Lights and numbers | RGB/RGBW/RGBWX channel counts, preserved X, independent raw W/X edits, brightness restoration and auxiliary intensity |
| Selects and media player | Exact file routing behind extensionless labels; separate scenes/playlists; browser IDs remain full filenames; stale/ambiguous selections rejected |
| Buttons and coordinator | Per-controller serialization, immediate state reconciliation, no automatic output retries, explicit file refresh |
| Setup and lifecycle | Multiple entries, default-port form round trip, independent failure/recovery, reload/unload without stopping the peer |
| ADAR | Separate shared scanner, verified device identities and authenticated API setup; discovery-only protocol operations |

## Earlier read-only physical check

The combined candidate discovered both physical controllers through ADAR and authenticated two real HA entries. The A4 reported RGBWX with **38 registered entities**, and the E16 RGB with **27**. Both loaded all seven platforms with disjoint entity IDs and the expected hardware capability filtering. Three simultaneous polling cycles, entry reload, peer polling after unload, and final scanner shutdown passed.

The physical check issued **48 read-only API requests**. A transport guard rejected every request outside constant/config/status/statistic reads and file listing. No operating controls, IP configuration, recovery, firmware, reboot, uploads or deletions were performed in this audit. Output commands, address substitution and partial failures were tested against HTTP simulators. Earlier physical operating tests are separate evidence and do not qualify the final changes automatically.

## Reconnected paired bench, 23 October 2026

The restored network exposed two additional issues. This follow-up was implemented and tested by the primary AI agent; the earlier independent audit does not cover these new changes.

- The RGB E16 returns four colour values, including unused W, even after a three-channel RGB write. Both controllers also store five-value palettes. The readers now validate the complete reported vectors and ignore channels outside the configured pixel type, so RGB palette recall remains usable. Missing required channels and malformed values remain rejected. Outbound vectors still require the exact configured channel count. API v1.9 Table 46 (page 79) limits the use of W/X to the corresponding pixel types.
- Verified HTTPS on port 4443 fails on both controllers with Python certificate verification code 20 under the default HA trust store. The client and setup flows now report fixed certificate-specific errors instead of masking this as a generic connection failure. No verification bypass, trust-store changes or HTTP fallback was introduced.

That earlier feature source passed **195 local tests** on Python 3.14.2 / HA 2026.10.2. Eight localhost TLS cases cover verified initialization/authentication, rejection before HTTP data for an untrusted issuer, wrong address, unsuitable purpose and expiry, plus documented default/override ports. Synthetic TLS fixtures contain no controller certificates or credentials. The Linux-specific custom-component pytest plugin cannot run on this Windows host; those separate contribution tests remain unqualified here. The earlier 96% coverage figure applies to the previous safety audit, not this follow-up revision.

The final paired physical feature run passed **34 stages**, recording **798 client exchanges including 69 operating writes**. It verified distinct RGB/RGBWX colours, raw W/X edits, preserved X during picker changes, independent brightness, restoration from Blank/black, preserved Live/File playback, palette recall, auxiliary intensity/priority, freeze, extensionless scene/playlist routing, button and media-player transport, restart, file refresh, browser labels and reload/unload isolation. Next/previous/restart required repeated status observations within a two-second bound; test tooling repeated only reads, never dispatched writes. The normal HA polling schedule is unchanged. The bench transport guard added independent MAC checks and an operation allowlist, so these counts are test traffic rather than a normal polling-rate estimate.

Earlier halted attempts and their restoration traces were retained. One exposed the real palette-length rejection; the other expected an RGB status vector of three values instead of the four returned by the controller. Both attempts restored the agreed Live baseline before a new run.

Both controllers were read back in the agreed temporary Live state with Pixel priority Hi/factor 255 and Aux priority Lo/factor 255. HA processes and polling were stopped before releasing exclusive access. Existing media and Node-RED-owned fixtures were not modified. The shared coordinator subsequently removed its owned test files and restored both original colours. A final **77-exchange read-only HA check** verified the E16's padded RGB state as `(186, 48, 255)`, the A4's original green, parallel polling and reload/unload isolation. HA was stopped again before releasing the bench.

The separate ADAR source passed **233 local tests**, then discovered both physical MACs and completed real discovery-confirm flows, three simultaneous polling cycles and reload/unload isolation with **77 read-only client exchanges**. Both branches' actual HA setup flows returned the specific `certificate_untrusted` error for the physical HTTPS failure. These checks qualify the failure handling, not successful hardware HTTPS. The final check also loaded an authenticated Advatek root into a separate in-memory stock Python context with certificate and hostname verification retained. Both controllers then failed purpose verification (code 26), so CA trust alone does not qualify this hardware path. The root matched an independently extracted copy from the Valid Authenticode-signed Advatek Assistant 1.1.4 installer; at that stage no production CA or proprietary code was bundled. Device-specific TLS, supported Linux checks, human review and emitted-light qualification were still open at that checkpoint.

## Advatek HTTPS follow-up

The custom integration now has an explicit Advatek HTTPS profile, with a user-provisioned controller MAC and an embedded authenticated public root. Full strict path validation and explicit vendor usage/identity constraints precede leaf pinning on the API connection. Port 4443, no HTTP downgrade, no redirects and no operator POST replay remain enforced. [The HTTPS profile](https.md) distinguishes API-documented requirements from the observed certificate policy, records installer/root provenance and lists session, clock and revocation limits. Existing entries do not silently opt in.

The final candidate passed **264 local tests**, including two actual HA TLS simulator entries, setup/reconfiguration, all seven platforms, independent controls, reload/unload, strict rejection before application bytes, certificate substitution, cached expiry/renewal and timeout/cancellation. Both archived physical certificate paths passed offline validation. Ruff, whitespace, wheel/source builds and wheel payload/import checks passed. A separate read-only AI reviewer closed the cached-renewal, parser-error, cancelled-worker-test and conventional-pin error-handling findings, then found no remaining blocker for a live test. The primary agent executed the tests; this is not independent hardware certification.

The first physical matrix loaded both HTTPS entries, rejected both swapped MACs, completed three parallel polling cycles and passed three A4 colour/X stages. It stopped when the harness's entity-enabling step triggered HA's native delayed reload during controls. It remains a failed run. Both controllers were restored, HA stopped, and the coordinator independently verified full original state and media preservation. The reviewed harness correction waits for native reload completion and verifies replacement coordinators before baseline capture or control writes. No integration-code fix was indicated by that trace.

The corrected full HTTPS rerun passed **14 stages** on the A4-S (RGBWX) and E16-S (RGB), both firmware 3.15.0. It completed in 138.6 seconds with **393 client exchanges including 21 operating writes**. Both real HA entries loaded all seven platforms, rejected swapped MACs, completed native entity-enable reloads and three parallel polling cycles, and passed sequential colour, raw X/picker preservation, brightness, Blank/Live, file refresh and peer-preservation checks. Explicit reload/unload isolation also passed. Status observations repeated reads only; no dispatched operator write was replayed. These guarded test counts are not a normal polling-rate estimate.

Both original Color parameter objects, intensity factors/priorities, identify state, full configuration and scene/playlist catalogue hashes were read back equal to the fresh baselines. All HA clients and polling were stopped before releasing ownership. The tested integration/dependency source digest is `aa87cbc5971e7fb07a502bb162a8c5f33a99b1a5dd308310491d496c5e9986f1`. The matrix used no uploads, deletions, configuration writes, ADAR, Identify, IP changes or recovery. Media transport controls were not repeated in this media-free HTTPS batch; their earlier HTTP evidence is separate.

The Windows log retained one Proactor `connection_lost` callback `WinError 10054` after a peer close. The installed CPython callback calls `shutdown()` before socket-close bookkeeping, so this exception leaves possible resource retention unresolved. The log does not identify the socket or establish whether capture or aiohttp owned it. No API exchange or operating acknowledgement failed in association with it, and it was not suppressed. This requires platform/endurance follow-up and prevents claiming a clean Windows endurance run or Linux qualification. The only recorded client exceptions in the successful matrix were the two intentional wrong-MAC certificate rejections.

Before commit, the coordinator independently read back the full original Color parameters, configuration, intensity factors/priorities, identify state and complete media inventories (16 A4 files, two E16 files), confirming all temporary fixtures absent at 13:40:58 UTC on 23 October 2026. A separate AI reviewer rechecked the saved live report, recomputed baseline equality and verified all source hashes, finding no blocker for this scoped draft change. Supported Linux, endurance and human review remain release gates.

## Remaining release limits

- Over HTTP, a MAC read and a later output write are separate protocol operations. That guard reduces accidental address substitution risk but cannot prevent deliberate MAC impersonation. The opted-in HTTPS profile additionally binds each API connection to the Advatek-signed certificate for the provisioned MAC; compromised device keys or CAs remain outside that guarantee.
- Repeat verification against the final merged/rebased revision and a supported Linux installation. RGBW installations, other model/firmware combinations, routed/multiple-interface discovery and endurance remain qualification work.
- The staged `core/` candidate is monitoring-only. This audit does not add its missing reauthentication/reconfiguration flows or qualify it for Gold. Public dependency licensing/releases, target Core checks, scope separation and human review remain required before upstream submission.
- RGBWX is not advertised as calibrated RGBWW or Kelvin/CCT control. API acceptance is not emitted-light calibration evidence.

## References

- Advatek Lighting, *PixLite Mk3 API v1.9*, 17 June 2026: section 7.2.2 (constant reads), section 7.9.5 (file listing), and playback/programmed-intensity definitions. The shared versioned PDF is authoritative; it is not redistributed here.
- Advatek Lighting, *Advatek Discovery and Recovery Protocol V1.0*, 22 October 2021, sections 2 to 5.1.
- Home Assistant Contributors, [data fetching and coordinators](https://contributors.home-assistant.io/core/integrations/fetching-data/), [unique entries](https://contributors.home-assistant.io/core/quality-scale/unique-config-entry/), [entry unloading](https://contributors.home-assistant.io/core/quality-scale/config-entry-unloading/) and [test coverage](https://contributors.home-assistant.io/core/quality-scale/test-coverage/), accessed 23 October 2026.
