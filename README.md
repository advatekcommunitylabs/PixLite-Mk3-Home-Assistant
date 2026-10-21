# Advatek PixLite Mk3 for Home Assistant

First-pass local custom integration, version 0.1.0. Add one entry per controller; controllers have independent connections and polling. Device and entity IDs use the controller MAC address, so names and IP addresses can change without creating new entities.

## Install

1. Copy `custom_components/advatek_pixlite` into your Home Assistant configuration directory, resulting in `/config/custom_components/advatek_pixlite/manifest.json`.
2. Restart Home Assistant.
3. Open **Settings > Devices & services > Add integration > Advatek PixLite Mk3**.
4. Enter the controller IP address/hostname, user (`admin` or enabled `oper`) and password. An empty password is supported. HTTP defaults to 80; HTTPS defaults to 4443. Leave the optional port blank for these defaults.
5. Repeat for each additional controller. Assign each device a useful name and area.

Requires a controller advertising API **v1.9** and a modern Home Assistant installation supporting config entry `runtime_data`. Intended baseline: Home Assistant 2025.1 or later; full HA runtime compatibility has not yet been verified. Use **Reconfigure** on the integration entry after an IP address or password change. A replacement controller with a different MAC should be added separately.

## Controls and monitoring

- **Showtime file** select lists `.scn` scenes and `.pl` playlists on the microSD card. Selecting a file starts it immediately and loops indefinitely (`cnt: 0`). Selecting it again via an action restarts it.
- Buttons: Blackout, Freeze outputs, Return to live input, Pause, Resume, Restart current mode, Previous/Next playlist item, Refresh Showtime files.
- Sensors: temperature, CPU usage, input/output frame rate, operating mode, playback filename, input bank voltages, and supported per-output currents, voltages and power status.
- Binary sensors: playback error and playback paused.
- Status and measurements refresh every 10 seconds; the file list refreshes every 60 seconds. Commands request an immediate refresh. Disconnected controllers become unavailable and polling retries automatically.

Blackout blanks the controller outputs; it does not remove electrical power. Return to live input restores configured streaming input. Pause/Resume require an applicable file playback, and Previous/Next require a playlist; invalid commands return a controller error. Restart current mode can also restart recording if recording is active. The API's `Stop` only exits transient modes and is deliberately not presented as a universal stop button.

Missing microSD cards do not prevent monitoring. File lists may remain cached during recording or formatting. New files appear automatically; use Refresh Showtime files to request an earlier refresh. The file sensor shows the selected top-level playlist/scene, not the current child item in a playlist.

## Automation example

Use your actual entity ID from the device page:

```yaml
alias: Evening pixel show
triggers:
  - trigger: sun
    event: sunset
actions:
  - action: select.select_option
    target:
      entity_id: select.garden_pixlite_showtime_file
    data:
      option: "Evening.pl"
```

For several controllers, target multiple select entities if they contain the same filename, or use separate actions for different filenames. This is automation-level triggering, not frame-synchronized playback across controllers.

## Transport and scope

All traffic stays on the local network. The API authenticates with Base64URL(SHA256(password)) query parameters, not HTTP Basic Auth. HTTP sends that reusable credential hash without encryption; use a trusted local network or configure HTTPS with the Advatek CA trusted by the HA environment. Certificate checking is never disabled. Credentials are stored in Home Assistant's config entry storage, and should be protected along with backups. Client errors intentionally omit request URLs.

This implementation uses HTTP polling; Advatek recommends WebSockets for push updates, which is a future improvement. No automatic network discovery, firmware updates, scene creation/uploads, pixel mapping changes, per-pixel streaming, or physical-controller configuration changes are included. Scenes/playlists must already exist on the controller. Adding/reloading the integration only reads data; output changes require an explicit entity action.

## Validation

`tests/test_api.py` runs the actual aiohttp client against a local HTTP simulator. It checks authentication encoding, version gating, endpoint/message formatting, serialization, file enumeration, result-less responses, and HTTP/API failures. It does not boot Home Assistant or substitute for hardware testing.

```sh
python -m pip install aiohttp pytest pytest-asyncio
python -m pytest tests -q
python -m compileall -q custom_components
```

Before relying on automations, test one controller: add it, compare readings with its UI, start a known scene, pause/resume, blackout, restore live mode, unplug/reconnect the network, and test a second controller independently. Test missing SD media, credential changes and DHCP changes as well. No physical controller or running HA instance was available during development.

## References

Implemented from the supplied **PixLite Mk3 API v1.9, V20260617**, especially sections 4, 6, 7.2, 7.7-7.9, 7.13-7.15. The PDF is not redistributed.

Home Assistant developer references: [config flows](https://contributors.home-assistant.io/core/integrations/config-flow/), [coordinated polling](https://contributors.home-assistant.io/core/integrations/fetching-data/), and [select entities](https://contributors.home-assistant.io/core/entities/select/).
