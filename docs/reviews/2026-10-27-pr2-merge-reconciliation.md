# PR #2 merge reconciliation, 27 October 2026

Fully AI-generated implementation and review. Human review remains required. Only reviewed and verified changes should be added. PR #2 remains draft.

## Source reconciliation

Merge `6748a07912a3d12f721356111e0a72390b07c9f8` (Sam's merged PR #1, head `09fea8cbb74bc854e4b8e6b8e724f060ae383988`) into PR #2 at `35342df71a61429ffaeb2b6e7733cb8b7f589c1d`. Preserve the merge history rather than rewriting reviewed commits.

The initial conflict resolution matched all 22 integration/dependency files from the [26 October paired verification](2026-10-26-reconciled-client-verification.md), whose Git LF digest is `e7075172e0b25f9214e29007151d6eb216e8d8438b782b634da6aa7a3fed121d`. Actual HA form tests then exposed the saved-port gap described below. The final candidate changes only the configuration flow and its port help text in strings/translations. The protocol client, TLS verifier/root, coordinator, manifest and runtime dependency declaration remain unchanged.

| Conflict | Resolution |
| --- | --- |
| API client | Keep the `_client` package and compatibility wrapper. The strict error-code and metadata validation was already backported in `35342df`; do not replace the TLS-capable client with the older monolithic HTTP client. |
| Configuration flow | Keep the current HA target, independently supplied controller MAC and certificate errors. Retain Sam's explicit `0 = protocol default` sentinel, normalized to saved `None`; `data_updates` preserves unrelated saved data. |
| Coordinator | Keep identity checks before polls and each individual output request, fresh colour snapshots under the controller lock, immediate state refresh and no replay after partial delivery. |
| Manifest and translations | Keep pyOpenSSL, HTTPS configuration/error text, colour controls and the existing codeowner. |
| Protocol/control tests | Retain both branches' additional regressions. Normalize identity through initialization, exercise invalid JSON in the shared simulator, and assert identity-check attempts without relying on the older coordinator's cached flag. |
| Actual HA tests | Retain Sam's `tests/ha` cases and explicit-zero/default round trips. Adapt extensionless labels, identity error wording and explicit enabling of optional diagnostic sensors to the current interface. |
| Guides and workflow | Distinguish historical HA 2025.1.1 evidence from this branch's HA 2026.10.2 target. Retain the manual-only workflow, align its Python/dependency target, and leave repository Actions disabled. No CI was dispatched. |

The Advatek pinned root, full path validation, provisioned MAC identity before HTTP, literal-address restriction, request deadline, cancellation handling and no HTTP fallback are unchanged. Both conventional TLS and Advatek-specific security test suites remain present.

## Verification

The first protocol stage passed 222 tests. The following actual-HA stage passed 41 and failed six port-clearing cases: four HTTP/HTTPS reconfigure/reauth cases and two unrelated-data preservation cases. HA applies `data_schema(user_input)` before the handler; omitting a port seeded with default `8080` therefore retains `8080`. The direct-handler probe bypassed that boundary. The failed attempt and assertions are retained. The fix restores the explicit zero sentinel already present in Sam's branch, while preserving this branch's HTTPS fields.

The Windows bootstrap was also corrected to import HA before pytest dependencies, so HA can establish its validation-library compatibility alias first. The earlier import-order warning is absent from the corrected HA run and is not asserted as the port failure's cause.

The corrected source passed 222 protocol/control cases, 47 actual-HA cases and 139 colour/file/runtime/TLS cases in attempt 04. Four additional Core/export checks initially failed because isolated Python startup deliberately skipped the development package's editable-install `.pth` file. Attempt 05 supplied an explicitly bound, byte-identical source copy of the actual standalone client and all four checks passed. No package was installed, no fake classes were substituted and no assertions were skipped. The 412 passing cases are evidence across these two runs, not one 412-case run. Failed attempts remain retained. The full Core plugin suite, Linux checks and physical operating tests are separate scopes.

Focused lint passed for the configuration flow and changed tests/probes. Lint identified one unused `deepcopy` import in the retained HA tests; removing that import changed no assertion or runtime code. The 412 cases precede that nonfunctional removal. The private hardware harness separately passed 80 guard cases, including eight canonical active/kind/scope refusals, 16 launcher rejection cases and cleanup of eight real loopback TLS transports. Earlier launcher/date-parsing, Ruff invocation and withdrawn harness attempts remain retained; these are separately accepted results, not one clean batch.

## Hardware and deployment limits

Fresh paired read-only verification passed before commit on 27 October, from 23:53:02 to 23:54:34 UTC (92.4 seconds), using Windows CPython 3.14.2 and actual HA 2026.10.2. Both A4-S and E16-S controllers ran firmware 3.15.0 and began in Live Data mode with Identify off. Provisioned-MAC and pinned-root HTTPS validation passed; two deliberately wrong MACs were refused.

Both controllers passed actual HA setup across seven platforms, native entity-enable reloads, three paired polls and reload/unload isolation. All four reconfigure/reauth form submissions replaced an explicit saved port `4443` with `0`, saved `None`, reloaded HTTPS port `4443`, retained the expected MAC and left the peer coordinator intact. The offline form tests separately cover an `8080` override and HTTP defaults; the hardware test does not claim another physical listening port.

There were 167 logical read-attempt records, including the two expected certificate refusals. All original saved status/configuration/catalogue fields matched final readbacks, including unknown fields. Both full configuration and catalogue hashes were independently recalculated. The A4's 16 and E16's three catalogue records were preserved, including the user's E16 test playlist. Catalogue metadata equality does not verify media file contents. No operating, settings, media, Identify, discovery or network writes were sent.

All 184 tracked TLS transports had closed sockets, cleared references and completed cleanup. The supervisor exited normally with code zero, without force; fresh checks found no owned parent, child, descendants or owned sockets. Standard custom-integration and optional zlib-acceleration warnings remain visible in stderr. No loop/callback error or traceback was recorded. The coordinator independently reconciled the raw evidence, accepted stopped release and cancelled the grant; a second source/evidence reconciliation confirmed the result without another device run.

The tested Windows source digest is `9c6cac47bd04ef9fa84278570581a084c3d6d88cf65d8fbb064aab827279a7c2`. The private v4 harness is `264b27853fe7bc1172a2726eeda1d1776dda7362f7bc50b78a388ec1607f2a57`, supervisor `490e5dd193c5534941fa32dd693de1ee02cf8d9d341a07ef11632ef073503a75`, report `b36650456d7795eb7c0b07878a449f67644d3485eeddec8a74452052e670703b`, and coordinator verification `581836f62902e01f659ba212d06fdb391c8970730dfbfa63bbcd11361161ab40`. Private raw evidence and every attempt are retained under `.build/ha-merge-port-clear-hardware-20261027-v4` and `.build/ha-merge-pr2-20261027`. These results do not repeat operating-control, emitted-light, endurance or other firmware/model qualification.

All 22 staged integration/dependency files equal the tested Windows bytes after CRLF-to-LF normalization only. Their Git LF digest is `2940eeafb0bc676978b9f6d82a5c6829782dd6c705095279a8e9fa5fabe95f4d`; the full per-file mapping is retained privately with the verification evidence.

The isolated Windows cleanup correction remains private and absent from the integration and installed interpreter. Its callback hash is `1180abffc010ce51d0188e9b0419d113e38cac76545bdf95e14ee1fd07797469`; the installed callback remains `cd6c4afcb912b68787bbf981f19a9510fb11d455f386d931742b4a0948319571`. The user chose to await a maintained fix. Supported runtime deployment remains unresolved, and PR #2 stays draft. No Linux, file deletion, CI dispatch or automatic review was used for this reconciliation. The manual-only workflow inherited from PR #1 is retained with Actions disabled at repository level.
