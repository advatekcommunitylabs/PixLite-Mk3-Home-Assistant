# Per-device safety audit follow-up

23 October 2026. This fully AI-generated follow-up was reviewed by a separate read-only AI auditor. It is not a human audit or third-party certification. Only reviewed and verified features should be added or merged.

The shared fixes check the saved MAC through authenticated reads before polling and every output request, reject malformed version/MAC payloads, clear an omitted custom port without breaking later reconfigure/reauth forms, respect the file-list cooldown after handled errors, and make explicit file refresh immediate. Every request within a multi-request action is checked; a changed identity stops the remaining writes. Output requests are not retried.

The local suite passed **225 tests** on Python 3.14.2 / HA 2026.10.2, including the new real-HA/two-HTTP-controller safety suite. Ruff error checks and whitespace checks passed. Dependency warnings remain. These are local checks, not GitHub CI or complete Linux/Core qualification.

A local combined candidate using PR #2 feature code with this branch's ADAR setup/discovery passed **168 custom integration tests**. A read-only physical check discovered and authenticated A4 and E16 simultaneously, loaded all seven platforms (38 A4 entities with RGBWX and 27 E16 entities with RGB), completed three concurrent polling cycles, and preserved peer polling through reload/unload. It made 48 read-only API requests. No device operating controls or configuration changes were issued during this audit.

The positive-brightness restoration and current colour/file-label behaviour belong to PR #2. This ADAR branch deliberately retains its older colour implementation. It must consume those feature fixes before a combined release. Repeat verification on the final merged/rebased revision.

The identity read and output write are separate API operations; MAC preflight cannot provide atomic identity binding or prevent deliberate MAC impersonation. The earlier physical output validation in `multiple-controllers-validation.md` is historical evidence, not a final-revision qualification.

See PR #2's `docs/per-device-audit.md` for the full findings and evidence matrix, including staged Core export limitations. No Core, Bronze or Gold readiness is claimed. Human review, supported Linux networking, final physical output qualification, public licensed dependency releases and target Core checks remain open. GitHub Actions stays disabled; no workflow or automatic agent run is requested.
