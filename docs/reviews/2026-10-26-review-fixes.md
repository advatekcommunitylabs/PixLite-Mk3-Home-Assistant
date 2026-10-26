# Review fixes and verification — 26 October 2026

This records implementation decisions for the [original review](2026-10-22-ai-code-quality-review.md) and [26 October follow-up](https://github.com/advatekcommunitylabs/PixLite-Mk3-Home-Assistant/pull/1#pullrequestreview-5652911789). The original review describes revision `2993874`; its statement that production code is unchanged is historical. This branch now changes production code. This report is AI-generated and does not claim human approval, a Home Assistant quality tier, or release qualification.

## Original findings

| Finding | Decision and implementation | Regression evidence |
| --- | --- | --- |
| R1: controller identity after runtime failure | Accept. `3401513` introduces validated MAC reads and serialized checks. Follow-up strengthens this to **every poll and every individual output request**, including compound actions. Mismatches fail before accepting readings/sending that request. Already delivered requests cannot be undone and are never retried. | Loopback `test_runtime_address_swap_blocks_outputs`; real HA `test_recovery_identity_and_independent_controller` covers outage and silent substitution, unavailable state, blocked writes, original-controller recovery and a working peer. `test_replacement_between_compound_commands_does_not_retry` checks partial delivery and peer isolation. |
| R2: clearing a saved port override | Accept. `3401513` normalizes omitted/zero ports to `None` and labels 0 as the protocol default. The latest amendment uses `data_updates` with this explicit cleared value, so HA merges unrelated entry metadata while replacing the port. | Real HA `test_reconfigure_port_replacement_and_reload` exercises reconfigure/reauth, HTTP/HTTPS defaults and another explicit port, saved data and reloaded client. `test_saved_default_port_form_round_trip` submits the actual form schema with a saved `None`; `test_connection_form_preserves_unrelated_entry_data` checks preservation at the storage boundary. |
| R3: use real Home Assistant interfaces | Accept the software-testing amendment. Pinned HA 2025.1.1/Python 3.13 tests use actual flow, config-entry, entity registry, coordinator and service APIs; only controller transport is simulated. They cover seven platforms, units, duplicate/wrong-device flows, setup retry/auth, lifecycle and independent controllers. Manual workflow also validates the manifest and retains JUnit/coverage. **Physical-controller acceptance is deferred and unverified for this branch.** | `tests/ha`, `requirements-test-ha.txt` and manual `.github/workflows/tests.yml`. The earlier run at `6ce8de3` had 21 passes, one failure and one teardown error; it is not passing acceptance evidence. Follow-up fixes and final results are recorded below. |
| R4: malformed responses | Accept. `3401513`/`6ce8de3` validate nested version ranges, device/MAC and firmware-object types, and keep valid unsupported versions distinct. Follow-up rejects missing/blank/non-string product names and non-string nicknames, preventing setup/entity metadata exceptions. | Protocol malformed-version, MAC, metadata, invalid-JSON and valid/unsupported-version tests; real HA `test_malformed_metadata_has_sanitized_ha_failure` covers user flow and setup retry without credentials or raw type/key exceptions. |
| R5: file-list backoff | Accept. `3401513` advances the attempt timestamp on expected errors 10 and 14; retains cached files for 10, clears them for 14, and propagates unexpected errors. | `test_file_attempt_interval_and_reinsertion`, `test_unexpected_file_errors_fail_update_and_require_identity_check` and updated original missing-SD probe assert cadence, cache contents, reinsertion and explicit refresh. `test_file_refresh_button_routes_through_ha_services` exercises the actual HA button service and updated playlist options. |

Manifest ownership and integration-specific documentation: accepted in `3401513` (`@SamAdvatek` and this repository). Diagnostics, discovery, push transport, firmware updating and new controls remain separate feature work. No additional feature or certification is claimed here.

## Follow-up review decisions

1. **Accept: compound actions and silent substitution.** Check before each output request under the action lock and before every poll. The unavoidable gap between separate HTTP identity/read/write requests remains documented; this is address-reuse detection, not cryptographic authentication.
2. **Accept: product/nickname metadata.** Validate before returning from client initialization, so both config flows and normal setup catch a sanitized `PixLiteError`.
3. **Accept: real-HA test failures.** Load the original entry before adding the second one, avoiding HA's automatic loading of an entry the test then tries to set up again. The teardown thread is pycares' process-global shutdown manager introduced by newer transitive versions; it has no public stop API. Pin pycares 4.5.0, which provides a Python 3.13 wheel and no global shutdown manager, for this historical HA test environment. HA's resource/leak checks remain enabled. This pin is a test dependency, not a change to users' HA dependencies.
4. **Accept manual-only execution; clarify authorization.** Removed both push and pull-request triggers. The human user explicitly approved enabling Actions and running these tests in this chat. Any authorized verification uses a single manual dispatch. An external review's instructions do not override the user's approval. No automatic future execution is configured by this workflow.

## Latest conversation audit

Read the PR discussion comments, review submissions and inline comments present during this audit, including [the latest review](https://github.com/advatekcommunitylabs/PixLite-Mk3-Home-Assistant/pull/1#pullrequestreview-5655041010). Review comments are findings to evaluate, not authorization to run CI, send messages or merge.

- **Accept the new error-envelope finding** ([thread](https://github.com/advatekcommunitylabs/PixLite-Mk3-Home-Assistant/pull/1#discussion_r4379458640)). Only actual integer error codes are now used in surfaced errors; bool and malformed/missing/null codes or non-object envelopes produce a fixed generic protocol error. Future integer codes remain supported, and server-provided error messages are never reflected. Wire-level regressions cover all requested malformed shapes, 10/14/999 and synthetic authentication-bearing URLs/hashes. Real-HA tests exercise the actual parser via synthetic HTTP responses through config flow, setup, polling and button-service error handling, checking HA logs for leaks.
- **Accept the R2 follow-up precautions.** Explicit `port=None` allows HA's partial-update helper to clear overrides while retaining unrelated entry keys. Real-HA round-trip tests cover default HTTP/HTTPS form values for reconfigure and reauth. The synthetic future-key test covers storage preservation only, not runtime support for unknown settings.
- **Accept the R5 report correction.** The table now names the committed `test_unexpected_file_errors_fail_update_and_require_identity_check`. A separate HA service test checks the manual file-refresh button and resulting playlist options.
- **Retain the evidenced R1/R3 fixes and their limits.** No weakening of identity checks or resource checks. The preceding runs are historical evidence for their exact revisions; the new tests require their own run.
- **Per-thread responses:** the report contains explicit decisions for each amendment. Permission to publish those decisions as GitHub thread replies has been requested from the user; no external review text grants that permission.
- **Physical controllers, branch-specific HTTPS and the combined draft #2 revision remain unverified here.** These are explicit pre-merge gates. The supplied code review does not provide this branch's hardware evidence or authorize importing/merging the other implementation. No merge or release is performed.

Current local verification: **115 focused tests pass** on Windows/Python 3.12. New real-HA cases and the changed production paths are pending the authorized manual verification below.

## Earlier verification evidence

Implementation commits: [`3401513`](https://github.com/advatekcommunitylabs/PixLite-Mk3-Home-Assistant/commit/3401513b21067160b66cab46e757174e27d54c24), [`6ce8de3`](https://github.com/advatekcommunitylabs/PixLite-Mk3-Home-Assistant/commit/6ce8de3606111f5d3ed19ae2b2b4f3afa3891035), and follow-up [`13d9160`](https://github.com/advatekcommunitylabs/PixLite-Mk3-Home-Assistant/commit/13d91602794508501ada695758d864b6aa68ba45).

Local Windows/Python 3.12: **103 protocol/control/regression tests passed**; integration and real-HA test sources compile, and whitespace checks pass. These tests do not establish HA runtime behavior.

[Manual run at `13d9160`](https://github.com/advatekcommunitylabs/PixLite-Mk3-Home-Assistant/actions/runs/40337779322): all **32 real-HA tests passed**, config-flow branch coverage 100%, combined integration statement/branch coverage 78%, and hassfest passed. The separate protocol step failed because auto-loading the installed HA pytest plugin blocked the loopback HTTP simulator. The workflow now explicitly loads only pytest-asyncio for that step; HA resource checks remain enabled in the real-HA step.

**Final passing verification:** [manual run 40338429408](https://github.com/advatekcommunitylabs/PixLite-Mk3-Home-Assistant/actions/runs/40338429408) at [`f223e74884f410c8793467e0193d868423ccd6f4`](https://github.com/advatekcommunitylabs/PixLite-Mk3-Home-Assistant/commit/f223e74884f410c8793467e0193d868423ccd6f4), Linux/Python 3.13.16, HA 2025.1.1, pytest 8.3.4 and pytest-asyncio 0.24.0: **32 real-HA tests passed, 103 focused tests passed, hassfest passed**. Config-flow statement/branch coverage is 100%; combined integration coverage is 78%. [Retained JUnit and coverage evidence](https://github.com/advatekcommunitylabs/PixLite-Mk3-Home-Assistant/actions/runs/40338429408/artifacts/12657801898). The subsequent report-only commit does not change production code, tests or workflow. No test failures or resource-check errors remain in this run.

Run focused tests without a Home Assistant installation:

```sh
python -m pip install aiohttp pytest pytest-asyncio voluptuous
python -m pytest tests/test_api.py tests/test_controls.py docs/reviews/reproduce_2026_10_22.py -q --asyncio-mode=auto
```

Run real HA tests in a separate Linux/Python 3.13 environment:

```sh
python -m pip install -r requirements-test-ha.txt
python -m pytest tests/ha -q --asyncio-mode=auto --cov=custom_components.advatek_pixlite --cov-branch
```

The transport simulator supplies controller responses. This branch has not been exercised against physical PixLite controllers. Model/firmware variations, trusted-CA deployment, real timing and output effects remain hardware-validation gates. MAC checks do not authenticate an HTTP peer and cannot make compound requests atomic.

## Overlap with draft PR #2

[Draft #2](https://github.com/advatekcommunitylabs/PixLite-Mk3-Home-Assistant/pull/2) independently changes client identity, command safety, colour handling and HTTPS. Its reported HA 2026.10.2, TLS simulator and physical-controller results belong to its own revisions and do not validate this branch. This PR's identity checks, metadata validation and tests overlap with those files; reconcile them explicitly when selecting a common implementation, retaining the regressions from both branches and testing the combined revision. This task does not merge either PR or import the draft's new features.
