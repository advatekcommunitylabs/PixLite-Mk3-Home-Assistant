# PR #3 merge reconciliation — 3 November 2026

Resolved conflicts between discovery head `009967ef0bba502f7b6d8b27140e57fba139b455` and main `8303f8f`. Main already includes PR #1's response validation and PR #2's reviewed client, HTTPS, colour and file-label changes. The merge preserves those implementations while adding ADAR setup and lifecycle handling. This is conflict-resolution evidence, not human approval or release qualification.

## Resolution

| Area | Result |
| --- | --- |
| Client, TLS, coordinator and controls | Retain main's `_client` package and compatibility wrapper, certificate validation, strict response/error-code validation, per-poll/per-request identity checks, fresh colour snapshots, immediate refresh and no output replay. These production files remain byte-identical to main. |
| Setup flow | Keep discovery/manual selection, scan results and authenticated ADAR identity confirmation. Retain main's provisioned HTTPS MAC field and certificate errors in manual, discovered, reconfigure and reauth forms. The trust MAC remains blank by default; unauthenticated ADAR data does not opt an entry into the vendor certificate profile. |
| Ports and address changes | Keep explicit `0 = protocol default`, saved `None` and partial entry updates. Tests cover preserving a saved port, HTTPS selection and provisioned MAC when discovery verifies a new address. |
| Manifest and translations | Combine the network dependency and discovery text with main's pyOpenSSL requirement, codeowner, documentation links, entity translations and HTTPS instructions. |
| Discovery lifetime | Retain one scanner shared by loaded entries, stop it after final unload/shutdown, and preserve current platform unload behavior. |
| Tests | Keep main's expanded API/TLS tests; they contain all discovery-branch test function names from the conflicted files. Adapt existing HA setup tests to select manual entry from the menu. Adapt concurrent scene/playlist tests to extensionless labels while checking the exact full filename delivered to each controller. |
| Documentation | Combine current HTTPS/colour documentation with discovery instructions and distinguish historical physical tests from this merged source. |

## Verification

Local Windows, Python 3.14.2, Home Assistant 2026.10.2, pytest-homeassistant-custom-component 0.13.373, pytest 9.0.3 and pyOpenSSL 26.4.0. Test dependencies are installed in an ignored workspace environment. HA is imported before pytest dependencies so HA establishes its validation-library compatibility alias. Automatic pytest plugin loading is disabled for the existing self-hosted runtime and protocol suites.

- **361 protocol/control/ADAR/TLS regressions passed**: `test_api.py`, `test_controls.py`, `test_adar.py`, `test_tls.py`, `test_advatek_tls.py` and the original review regression probes.
- The first combined actual-HA runtime batch passed **132** and failed **two** old selector assertions. Both failures used the former full-filename selector interface; one also supplied a playlist to the scene-only selector. Updating the fixture to include a scene and playlist and submitting extensionless labels retained full-filename wire assertions. The next focused run caught one dependent file-list assertion; that was corrected to assert both separate controller-specific records.
- The corrected `test_multiple_instances.py` passed **32** cases. Together with the **102 unchanged runtime cases** that passed in the first batch (`test_adar_homeassistant.py`, `test_device_runtime.py`, `test_colour_contract.py`, `test_file_display.py`), this provides **134 passing runtime cases** across the batches. The total is **495 distinct passing cases**, not one 495-case invocation.
- New merge-boundary cases verify that discovery confirmation accepts an explicitly supplied HTTPS identity and default port, and that authenticated address updates retain saved HTTPS settings and the original identity.
- Ruff E/F checks passed for the integration and changed test files. Source compilation, JSON parsing/translation equality, whitespace and conflict-marker checks passed.

JUnit evidence is retained locally in `.test-deps/pr3-protocol-results.xml`, `.test-deps/pr3-runtime-results.xml` (including the initial failures), and `.test-deps/pr3-multiple-instances-results.xml` (final passing focused run). No failures were hidden or skipped in these batches.

The separate plugin-based `tests/ha` suite could not start on Windows because the official plugin imports HA's Linux runner and requires `fcntl`. No replacement module or leak-check suppression was introduced. Its flow assertions are adapted to the merged menu, but this suite and the Core plugin suite still require Linux verification. The actual-HA self-hosted suites above executed without that Linux-only pytest plugin; they use real HA config managers, registries, entity platforms and services.

No CI was dispatched or repository Actions setting changed. No physical controller requests, operating writes or LAN discovery scans were sent. Runtime tests simulate ADAR and controller responses; real HTTP/TLS/UDP traffic is restricted to loopback. Earlier paired-device results remain evidence for their stated revisions. Production network deployment, physical operating qualification, the previously recorded Windows transport-cleanup issue and human review remain separate requirements. Resolving Git conflicts does not resolve those release gates or change the PR's draft status.
