# Fully AI-generated code quality review

This is a fully AI-generated review. No human review, physical-controller validation, or running Home Assistant validation is claimed. Only features that have been reviewed and verified should be added. Passing simulator or interface-double tests alone does not verify a feature in Home Assistant or on a PixLite controller.

Sam's agent must reply to every review comment and every suggested amendment. Each reply must state whether it accepts, rejects, or defers the point, explain why, and link any resulting commit and verification evidence. A rejection needs evidence or a reproducible counterexample. Deferred work must remain explicitly unverified. Do not resolve a thread merely because code was written or an agent agreed with it.

## Scope and evidence

- Repository: `advatekcommunitylabs/PixLite-Mk3-Home-Assistant`.
- Reviewed revision: [`299387422dadb7776359a1c5a59856469ca905e4`](https://github.com/advatekcommunitylabs/PixLite-Mk3-Home-Assistant/commit/299387422dadb7776359a1c5a59856469ca905e4), Sam Clay, 22 October 2026, 13:53:50 UTC. Manifest version: `0.4.1`.
- Read all 14 integration Python files, the manifest and translations, README, both test files, repository tree, and recent commit history. No tracked CI workflow was present; the Actions API returned zero runs when checked.
- Existing suite: **57 passed**. Review diagnostic probes: **5 passed**. All 14 integration Python files parsed successfully. Environment: Windows, Python 3.14.2, aiohttp 3.14.5, pytest 9.1.1, pytest-asyncio 1.4.0, voluptuous 0.16.0, installed in an isolated review environment.
- The five passing probes reproduce existing gaps. They are observations of the reviewed baseline, not evidence that the gaps have been fixed. After a fix, update or replace these probes with regression tests asserting the desired behavior.
- No controller traffic was sent. HTTP tests used a loopback server. No Home Assistant instance was started. Production integration files are unchanged by this PR.

Reproduce from the repository root in an isolated Python environment:

```sh
python -m pip install aiohttp==3.14.5 pytest==9.1.1 pytest-asyncio==1.4.0 voluptuous==0.16.0
python -B -m pytest tests -q -p no:cacheprovider
python -B -m pytest docs/reviews/reproduce_2026_10_22.py -q -p no:cacheprovider
```

## How the integration fits Home Assistant

Home Assistant Core provides the event loop, state machine, event bus, action registry, and persistent registries. An integration translates a controller into standard entities. Dashboards and automations then use those entities; they do not need to understand the PixLite protocol. This integration is loaded into Core as a custom integration, rather than running as a separate application. [HA architecture](https://contributors.home-assistant.io/architecture/core/)

The actual path is: config flow validates an address and credentials, setup initializes the API and checks the MAC, a shared coordinator polls one controller, and seven entity platforms expose that data and issue commands. Each config entry has its own client and locks. The MAC-based IDs preserve entity identity when names or configured addresses change.

| Component | Interpretation from the source |
| --- | --- |
| `api.py` | Async aiohttp client, `/ver` capability check, API v1.9 POST messages, query authentication, response-envelope validation, per-controller request lock. No HA dependency. |
| `config_flow.py`, `__init__.py`, `entity.py` | Manual UI setup, reconfigure and reauth paths, first refresh before platform setup, runtime data, MAC identity, device grouping and platform unloading. |
| `coordinator.py` | Status/statistics/config polling every 10 seconds; file-list cache intended for 60 seconds; a control lock serializes polling and compound actions. |
| `light.py`, `controls.py` | One aggregate pixel light. Brightness preserves the current mode. A colour command replaces playback with solid colour. Off sets intensity to zero; it does not remove power or stop playback. |
| `select.py`, `button.py`, `media_player.py` | Stored scene/playlist selection, palette selection, intensity priority, explicit playback controls, and a playlist browser/player. This is controller lighting playback, not audio streaming. |
| `number.py` | Auxiliary DMX output intensity sliders, added dynamically when the configured port mode permits them. |
| `sensor.py`, `binary_sensor.py` | System and output measurements, mode/playback details, paused and error state. Numeric measurement units are mapped and scaled in the sensor layer. |

This code does not send per-pixel Art-Net or sACN frames, upload scenes, edit pixel mapping, provide automatic discovery, or synchronize multiple controllers at frame level. Its role is automation and supervision of controller-resident playback. Sending a colour and brightness together uses two serialized requests, not an atomic transaction. The coordinator refreshes after partial failure and does not retry output commands.

The broad structure follows HA's documented coordinator and config-entry patterns. Sharing HA's aiohttp session, stable identity, explicit colour-mode handling, and keeping I/O out of entity properties are appropriate choices. HTTP polling is correctly declared as `local_polling`. Push would reduce polling and improve latency where supported, but converting to WebSockets is not a prerequisite for addressing the findings below. [Fetching data](https://contributors.home-assistant.io/core/integrations/fetching-data/), [config entries](https://contributors.home-assistant.io/core/integrations/config-entries/), [light entities](https://contributors.home-assistant.io/core/entities/light/)

## Actionable findings

### R1 [P1] Recheck controller identity after a runtime connection failure

Source: [`__init__.py:18-19`](https://github.com/advatekcommunitylabs/PixLite-Mk3-Home-Assistant/blob/299387422dadb7776359a1c5a59856469ca905e4/custom_components/advatek_pixlite/__init__.py#L18-L19), [`coordinator.py:26-45`](https://github.com/advatekcommunitylabs/PixLite-Mk3-Home-Assistant/blob/299387422dadb7776359a1c5a59856469ca905e4/custom_components/advatek_pixlite/coordinator.py#L26-L45), [`coordinator.py:54-64`](https://github.com/advatekcommunitylabs/PixLite-Mk3-Home-Assistant/blob/299387422dadb7776359a1c5a59856469ca905e4/custom_components/advatek_pixlite/coordinator.py#L54-L64).

The MAC comparison only runs during setup. Polling resumes against the configured address after a transport failure without rereading identity, and commands use that same address. If DHCP reassigns it to another compatible controller accepting the same credentials, HA can show that controller's readings under the original identity and send output changes to it.

Verified in the loopback probe: initialize controller A, fail a poll with HTTP 503, replace the endpoint with controller B, recover polling, and request Blank. B receives `modePlayback`, while the client's cached MAC remains A's. This verifies the software path, not the frequency of DHCP reuse in actual installations.

Suggested amendment: establish and verify the expected MAC when recovering or rebinding controller communication, block output changes until the check succeeds, and surface a mismatch as unavailable with a clear reconfiguration error. Serialize recovery verification with command dispatch. Document that an HTTP identity read is not cryptographic device authentication.

Acceptance evidence: a regression that substitutes another MAC after an outage must show zero output commands reaching the replacement; recovery to the original MAC and a second independent controller must still work. Validate the same sequence in HA and on approved test hardware. HA's [WLED troubleshooting](https://www.home-assistant.io/integrations/wled/#failed-to-set-up-the-device-due-to-mac-address-mismatch) documents the same DHCP identity hazard.

### R2 [P2] Allow reconfiguration to remove a custom port

Source: [`config_flow.py:33-53`](https://github.com/advatekcommunitylabs/PixLite-Mk3-Home-Assistant/blob/299387422dadb7776359a1c5a59856469ca905e4/custom_components/advatek_pixlite/config_flow.py#L33-L53), [`config_flow.py:68`](https://github.com/advatekcommunitylabs/PixLite-Mk3-Home-Assistant/blob/299387422dadb7776359a1c5a59856469ca905e4/custom_components/advatek_pixlite/config_flow.py#L68).

The successful reconfigure/reauth path passes `data_updates=data`. HA merges this mapping into existing entry data, so omitting the optional `port` cannot remove a saved override. The schema also seeds the existing port as a default. The UI needs an explicit and tested way to return to the protocol's default port.

Verified at handler level: with saved port 8080 and a submitted mapping without `port`, validation uses port 80, while the emulated HA merge keeps 8080. The probe emulates the helper; the full UI flow was not exercised. The actual merge contract was checked in HA Core [2025.1.0](https://github.com/home-assistant/core/blob/2025.1.0/homeassistant/config_entries.py) and [2026.10.2](https://github.com/home-assistant/core/blob/2026.10.2/homeassistant/config_entries.py).

Suggested amendment: define explicit default-port clearing semantics, normalize the submitted connection data, and use replacement data or an explicit cleared value so validation and saved configuration agree. Preserve the MAC identity.

Acceptance evidence: real HA flow tests for custom port to default, custom port to another override, HTTP/HTTPS default selection, reauth, reload, and readback of saved entry data. See [reauthentication and reconfiguration](https://contributors.home-assistant.io/core/integrations/reauth-reconfigure/).

### R3 [P2] Test the integration with real Home Assistant interfaces before claiming compatibility

Source: [`tests/test_controls.py`](https://github.com/advatekcommunitylabs/PixLite-Mk3-Home-Assistant/blob/299387422dadb7776359a1c5a59856469ca905e4/tests/test_controls.py), [`tests/test_api.py`](https://github.com/advatekcommunitylabs/PixLite-Mk3-Home-Assistant/blob/299387422dadb7776359a1c5a59856469ca905e4/tests/test_api.py).

The control tests replace HA modules, coordinator internals, entities, enums, and the shared entity base with doubles. They exercise useful protocol and action logic, but cannot establish registration, config-flow behavior, lifecycle cleanup, state serialization, or real service routing. Neither test file exercises the config flow, integration setup/unload, or the actual sensor and binary-sensor platforms. The stated HA 2025.1 baseline remains explicitly unverified in the README.

Suggested amendment: retain the protocol tests, add HA integration tests using the real `hass` fixture and `MockConfigEntry`, and mock the controller boundary instead of HA internals. Pin and state the versions actually tested. Add CI for those tests and manifest validation. Do not promote the intended version baseline into a compatibility claim without evidence.

Acceptance evidence: complete config-flow branch coverage; setup and first-refresh retry; duplicate and wrong-device handling; reauth/reconfigure; unload/reload with no leaked listeners; states, units and availability for all seven platforms; actions through `hass.services`; independent controllers. Then separately record controlled physical validation. HA's [testing guidance](https://contributors.home-assistant.io/core/development/tests/) and [quality scale](https://contributors.home-assistant.io/core/quality-scale/) are the reference criteria, not a claimed rating for this custom integration.

### R4 [P2] Keep malformed version responses inside the protocol error boundary

Source: [`api.py:91-105`](https://github.com/advatekcommunitylabs/PixLite-Mk3-Home-Assistant/blob/299387422dadb7776359a1c5a59856469ca905e4/custom_components/advatek_pixlite/api.py#L91-L105).

The response envelope is checked, but `initialize()` assumes nested `apiVer` items and their `min` values have the right types. `apiVer: [null]` raises `AttributeError`; `min: null` raises `TypeError`. Both escape the `PixLiteError` cases handled by setup and the config flow, so these malformed responses bypass the intended user-facing error handling. This is a robustness defect for malformed or unexpected endpoints, not a claim that normal PixLite firmware returns these payloads.

Suggested amendment: validate the version range, device object, and MAC types before use, and convert invalid shapes into sanitized protocol/device errors without including authenticated URLs. Keep unsupported valid versions distinguishable from connection failures.

Acceptance evidence: malformed nested types, missing/null fields, invalid MAC values, invalid JSON, unsupported valid versions, and valid API v1.9 data; assertions that setup and the config flow report the intended error without credential disclosure. The two diagnostic cases currently reproduce the escaping exceptions.

### R5 [P3] Apply the file-list interval to expected missing-card responses

Source: [`coordinator.py:36-44`](https://github.com/advatekcommunitylabs/PixLite-Mk3-Home-Assistant/blob/299387422dadb7776359a1c5a59856469ca905e4/custom_components/advatek_pixlite/coordinator.py#L36-L44).

`files_updated` advances only on a successful listing. Code 14 clears the list but leaves its timestamp unchanged; tolerated code 10 also leaves it unchanged. Once the cache is due, these expected responses therefore cause a new file-list request on every 10-second status poll, rather than the documented 60-second cadence.

Verified with missing-card responses at simulated times 1000 and 1010 seconds: two `fileList` attempts occur and the timestamp remains zero.

Suggested amendment: apply an explicit attempt interval or backoff to expected unavailable-media responses while retaining cached files where appropriate. Preserve the Refresh Showtime files override and a bounded delay for detecting newly inserted media.

Acceptance evidence: missing card, recording/formatting prohibition, normal successful listing, unexpected errors, card reinsertion, and explicit refresh. Assert the request counts and resulting file list.

## Verification limits and decisions

The API mapping was also compared with Advatek Lighting's supplied *PixLite Mk3 API v1.9*, document V20260617 (17 June 2026), sections 2, 4, 6.7, 7.9, 7.11, 7.13 and 7.14. The local official reference was read; the PDF is not redistributed in this PR. It supports the HTTP ports, SHA256/Base64URL authentication, response error handling, intensity ranges/priority, and statistic units used here. This source comparison does not prove implementation behavior on physical hardware.

HTTP authentication exposes a reusable password hash on an unencrypted connection. The README discloses that limitation, and the client keeps TLS certificate checking enabled and avoids returning request URLs in its caught transport errors. These are source-confirmed properties. Actual credential-rejection status codes, trusted-CA setup, device model variations, controller firmware behavior, timing under load, and HA runtime compatibility remain unverified.

Do not infer Home Assistant Core acceptance, a quality-scale tier, HACS/Marketplace acceptance, a security certification, or release readiness from this review. The manifest has empty `codeowners` and points its documentation field to a generic homepage; resolve ownership and integration-specific documentation if preparing distribution. Adding diagnostics, push transport, discovery, firmware updates, or new controls would be separate feature work requiring its own review and verification. [Manifest reference](https://contributors.home-assistant.io/core/integrations/manifest/), [diagnostics reference](https://contributors.home-assistant.io/core/integrations/diagnostics/)

Home Assistant references are official project documentation by Home Assistant contributors, checked on 22 October 2026. The quality-scale tiers and diagnostics pages displayed an update date of 16 October 2026. They are living documents, not evidence that this integration has completed their checks.
