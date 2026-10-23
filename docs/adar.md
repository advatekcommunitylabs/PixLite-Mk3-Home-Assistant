# ADAR discovery

The integration sends discovery requests on the IPv4 interfaces enabled in Home Assistant's network settings. Each scan uses multicast `239.255.251.1:49151`, receives on `239.255.251.2` at the request's ephemeral UDP port, then tries limited broadcast `255.255.255.255`. Requests exclude previously found MACs. Each interface has at most six half-second rounds and fifty responses; reaching either limit produces an incomplete result. Firewalls and container networking must permit this traffic. Scans do not cross NAT automatically.

Use addresses in the same subnet for a direct connection between Home Assistant and the controller. A routed connection requires working routes and firewall access; limited broadcasts remain on the local network. Discovery alone does not establish API reachability. See [RFC 1122, section 3.3.1.1](https://www.rfc-editor.org/rfc/rfc1122.html#section-3.3.1.1) (R. Braden, editor, October 1989) for local and routed delivery.

Only Advatek PixLite Mk3 devices advertising API v1.9, a web interface and normal operation are offered. Recovery devices and conflicting addresses for one MAC are excluded. Packet size, field types, identifiers and sender/reported addresses are checked. Discovery messages are unauthenticated; setup still requires an API connection and matching MAC. Discovery sends no network configuration, recovery, firmware or output commands.

## Setup and lifecycle

Adding the integration offers discovery or manual address entry. Empty and failed scans offer retry and manual setup. Incomplete scans label their results accordingly. Selecting a controller prompts for credentials, protocol and optional API port. Invalid credentials and identity mismatches cannot create an entry.

Once at least one controller entry is loaded, a single shared scanner runs every five minutes. Newly discovered controllers are offered through Home Assistant's integration discovery flow. Ignored devices remain ignored. An existing entry's address changes only after its saved credentials work at the new address and its API MAC matches the saved MAC. Saved credentials and the API port are preserved. Unloading the final entry or shutting down Home Assistant cancels discovery and closes its sockets.

Automatic discovery before the first entry is configured is not implemented. It needs a verified DHCP matcher or an agreed Home Assistant Core bootstrap mechanism. The manual setup scan remains available.

## Physical discovery validation

On 23 October 2026, the production discovery function found an A4-S Mk3 and an E16-S Mk3 in three consecutive scans from a Windows WiFi interface. Both advertised firmware 3.15.0, API v1.0 through v1.9, normal operation and a web interface. Both controller addresses and the workstation were on the same /24 subnet.

Separate multicast-only and limited-broadcast-only probes also received valid replies from both controllers. Broadcast delivered duplicate replies through the two receive sockets; the MAC-keyed collector returned each controller once. Each production scan sent three discovery requests, used exclusions after the initial replies, completed without conflicts and closed both transports. Outgoing payloads were checked to contain only ADAR Discovery Request `0x1201`.

With multicast transmission suppressed in the test harness, the unchanged production scanner found both controllers using its broadcast fallback. Cancelling a live scan propagated cancellation and closed both transports. These checks changed no host or controller network settings.

Home Assistant 2026.10.2 also ran its actual setup flow with live ADAR discovery on the selected interface. Both devices appeared in the selection form, and selecting each reached its credentials form with the correct address. The flows were then aborted without creating entries or submitting credentials. The adapter list was supplied explicitly for the WiFi interface; ADAR transport and controller replies were real.

No API credentials, HTTP requests, network-configuration messages, recovery messages, firmware uploads or output commands were sent. Sanitized captured replies for both models are retained in `tests/fixtures/` for parsing, duplicate-response and selection-flow regression tests. This verifies discovery on this Windows network and firmware combination; Linux/container networking and authenticated setup on physical controllers still require separate verification.

## Local validation

Use a dedicated Python 3.14.2 environment. The pinned test helper installs Home Assistant 2026.10.2 and its matching test dependencies:

```sh
python -m pip install -r requirements-test.txt
```

Disable automatic pytest plugin loading, then load only the required plugins. In PowerShell:

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = '1'
```

In a POSIX shell, use `export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`. Run the same test command in either shell:

```sh
python -m pytest -p pytest_asyncio.plugin -p pytest_cov.plugin tests/test_adar.py tests/test_adar_homeassistant.py tests/test_api.py tests/test_controls.py -q --cov=custom_components/advatek_pixlite --cov-report=term-missing
```

The ADAR tests mock interface socket configuration and use real UDP only on loopback. Home Assistant runtime tests use actual config managers, entity platforms and coordinator refreshes, with mocked controller responses, adapter enumeration and ADAR discovery. DNS uses a threaded resolver to avoid starting mDNS. No controller output commands are exercised by these runtime tests. The existing control tests use interface doubles, and the API tests use a loopback HTTP simulator.

Lint and format checks for the changed Python files:

```sh
python -m ruff check --isolated --select E,F,I,UP --ignore E501 --target-version py314 custom_components/advatek_pixlite/_adar/__init__.py custom_components/advatek_pixlite/adar_flow.py custom_components/advatek_pixlite/discovery.py custom_components/advatek_pixlite/config_flow.py custom_components/advatek_pixlite/__init__.py custom_components/advatek_pixlite/entity.py tests/test_adar.py tests/test_adar_homeassistant.py
python -m ruff format --isolated --check custom_components/advatek_pixlite/_adar/__init__.py custom_components/advatek_pixlite/adar_flow.py custom_components/advatek_pixlite/discovery.py custom_components/advatek_pixlite/config_flow.py custom_components/advatek_pixlite/__init__.py custom_components/advatek_pixlite/entity.py tests/test_adar.py tests/test_adar_homeassistant.py
```

## Standalone library and Core requirements

The bundled `_adar` directory has no Home Assistant dependency and can build independently as `advatek_adar`. Its packaging metadata deliberately prevents PyPI upload with the `Private :: Do Not Upload` classifier. Local build:

```sh
python -m build --outdir dist/adar custom_components/advatek_pixlite/_adar
```

Home Assistant Core requires protocol communication in a separate open-source library published on PyPI. An approved license, public source, tagged releases, issue tracking, release validation and automated publication are still required. Core should then depend on that distribution instead of the bundled copy. No publication pipeline is enabled here; GitHub Actions remains disabled. This implementation does not claim Core acceptance or a Gold quality rating.

Before release, verify multicast and broadcast on Linux in the intended Home Assistant deployment, each supported controller model and firmware, selected adapters, blocked multicast, duplicate replies, DHCP address changes, authentication failures and unload/shutdown cancellation. Loopback and local Windows runtime tests do not establish those behaviours on production networks or devices. Discovery's MAC verification applies to setup and discovered address updates. Continuous identity checking before output commands is not provided by this change.

## Protocol references

Advatek Discovery and Recovery Protocol V1.0 (2021-10-22), sections 2 to 5.1, defines the wire exchange. PixLite Mk3 API v1.9 (2026-06-17) defines API compatibility and authenticated controller identity. The supplied PDFs are not redistributed in this repository.

- ADAR PDF SHA-256: `fd82dd725b08dfd316a2b61935b47b3f600d4fb551c6672736d2fa9250c88b17`
- API PDF SHA-256: `f859f89a8fe1806181ff4a3bbd9c836559b42542cc760483a44cda7365976e41`

Official Home Assistant guides: [network interfaces](https://contributors.home-assistant.io/core/integrations/network-discovery/), [config flows](https://contributors.home-assistant.io/core/integrations/config-flow/), [integration discovery](https://contributors.home-assistant.io/core/integrations/discovery/), [library requirements](https://contributors.home-assistant.io/core/integrations/api-library/#requirements), and [quality scale](https://contributors.home-assistant.io/core/quality-scale/).
