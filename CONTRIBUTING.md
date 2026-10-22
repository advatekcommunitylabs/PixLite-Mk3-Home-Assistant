# Contributing

Keep changes focused and include tests for observable behavior. Use short functional docstrings and concise comments about non-obvious code behavior. Keep review history, agent instructions, approval claims, and internal project discussions out of production source files.

## Development

The contribution candidate targets Home Assistant 2026.10.2 and Python 3.14.2 or later. Home Assistant runtime tests require Linux. Use an isolated environment:

```sh
python -m pip install homeassistant==2026.10.2 pytest-homeassistant-custom-component==0.13.373 ruff==0.17.2 build
python -m pip install --no-deps -e .
python -m pytest tests/test_api.py tests/test_controls.py -q
python -m pytest tests/components/advatek_pixlite -q
python script/test_core_candidate.py
ruff check custom_components core script tests/components
ruff format --check custom_components core script tests/components
python -m build
```

Protocol tests exercise the real HTTP client against loopback. Home Assistant tests use its actual config-entry, state-machine, and entity-registry interfaces while mocking the controller boundary. The exported candidate is exercised separately through the custom-integration loader; that check does not replace tests and hassfest in the target Core checkout. Physical-controller verification is a separate requirement. GitHub Actions is disabled at the repository level to control credit usage. No workflow files are included. Do not add or enable credit-consuming GitHub automation without a new explicit request.

`custom_components/advatek_pixlite` is the complete custom integration. `core/advatek_pixlite` holds the smaller initial Core contribution. `script/prepare_core.py` exports the latter with shared sensor and entity implementations into `homeassistant/components/advatek_pixlite` and its tests into `tests/components/advatek_pixlite`. The protocol package contains only `_client`, independently of Home Assistant.

## Preparing a Core contribution

Follow Home Assistant's [contribution guide](https://github.com/home-assistant/developers.home-assistant/blob/master/docs/core/integration/contributing_to_core.md), [development checklist](https://contributors.home-assistant.io/core/development/checklist/), and [Core AGENTS.md](https://github.com/home-assistant/core/blob/dev/AGENTS.md). Check these living sources again immediately before submission.

The initial contribution has one platform, `sensor`, and only the code needed for monitoring. Keep light, select, button, number, binary-sensor, and media-player additions in separately reviewed follow-up PRs. Do not submit this entire repository or its internal review documents to Core.

Before exporting a submission, release the protocol client from a public source repository under an agreed OSI-approved license, using public CI, a matching tag, and PyPI wheel and source distribution. The proposed package is not published. Its `Private :: Do Not Upload` classifier must remain until release review and licensing are complete. Confirm the integration codeowner with Sam before upstream submission.

To inspect the draft tree before release:

```sh
python script/prepare_core.py --output dist/core-draft --client-version 0.1.0 --draft
```

The destination must not already exist. Without `--draft`, the exporter verifies the requested release and source distribution on PyPI. A generated tree is still a preparation artifact, not evidence of Bronze compliance or approval. Replace the version with the actual reviewed release when one exists.

In a human-owned Home Assistant Core fork, branch from `dev`, run `script/setup`, copy only the exported component and test directories, then run:

```sh
python3 -m script.translations develop --integration advatek_pixlite
uv run --no-sync pytest tests/components/advatek_pixlite
python3 -m script.hassfest
python3 -m script.gen_requirements_all
uv run --no-sync prek run --all-files
```

Include the generated requirements, CODEOWNERS, translations-related and integration registry files changed by Core's tools. Do not claim these checks passed based on this repository's Ruff or custom-loader tests. Complete all Bronze rules with evidence, including dependency transparency, brands, documentation, and full config-flow test coverage. Do not amend, rebase, or squash already-pushed commits while a PR is under review.

Use the complete current [Core pull request template](https://github.com/home-assistant/core/blob/dev/.github/PULL_REQUEST_TEMPLATE.md), retaining its unchecked boxes and required text. Explain the actual product, initial platform, API library source, release workflow and tag, verification, limitations, and linked documentation/branding PRs. The documentation PR goes to `home-assistant/home-assistant.io` against `next`; the Core PR goes to `home-assistant/core` against `dev`.

## Human submission and correspondence

Home Assistant's [AI policy](https://contributors.home-assistant.io/start/ai-policy/) requires a human to review, understand, and explain each change before submission. Autonomous upstream contributions are not accepted. The human contributor must answer maintainers' substantive questions themselves. This preparation does not authorize an automated upstream submission or certify that the human-review checkboxes are complete.

Manufacturer participation does not imply Works with Home Assistant certification. The existing Front conversation asks for contribution, documentation and branding guidance; it contains the outgoing request and no Home Assistant response at the time of preparation. Do not claim branding permission, certification, acceptance, or a promised listing from that request.
