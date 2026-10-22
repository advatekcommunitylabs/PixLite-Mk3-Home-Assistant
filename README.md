# Advatek PixLite Mk3 for Home Assistant

Local custom integration, version 0.4.1. Add one entry per controller; controllers have independent connections and polling. Device and entity IDs use the controller MAC address, so names and IP addresses can change without creating new entities.

## Install

1. Copy `custom_components/advatek_pixlite` into your Home Assistant configuration directory, resulting in `/config/custom_components/advatek_pixlite/manifest.json`.
2. Restart Home Assistant.
3. Open **Settings > Devices & services > Add integration > Advatek PixLite Mk3**.
4. Enter the controller IP address/hostname, user (Administrator or enabled Operator) and password. An empty password is supported. HTTP defaults to 80; HTTPS defaults to 4443. Leave the optional port blank for these defaults.
5. Repeat for each additional controller. Assign each device a useful name and area.

Requires a controller advertising API **v1.9** and a modern Home Assistant installation supporting config entry `runtime_data`. Intended baseline: Home Assistant 2025.1 or later; full HA runtime compatibility has not yet been verified. Use **Reconfigure** on the integration entry after an IP address or password change. A replacement controller with a different MAC should be added separately.

## Controls and monitoring

- **Pixels** light entity provides on/off, master brightness, a colour picker and transitions. Brightness-only commands preserve the current scene, playlist or live mode.
- **Showtime colour preset** selects one of up to 12 controller palette colours. It starts solid-colour playback, preserves the current intensity, and uses Showtime's configured fade time. Turn the light on if master intensity is zero. Presets are read from the controller and refresh with polling; editing/saving the controller palette is not included.
- **Intensity priority** selects Override live intensity or Yield to live intensity. Explicit light on/off/brightness commands take priority again. Yield allows incoming live intensity to win when available; otherwise the programmed factor applies.
- **Showtime file** select lists `.scn` scenes and `.pl` playlists on the microSD card. Selecting a file starts it immediately and loops indefinitely (`cnt: 0`). Selecting it again via an action restarts it.
- Separate **Play**, **Pause**, **Previous** and **Next** playback buttons with matching icons. Play resumes an existing file playback; choose a Showtime file to start a scene. Previous and Next navigate playlist items, not the file browser. Existing button unique IDs are preserved, including the former Resume button.
- Other buttons: Blank, Freeze, Live Data, Restart current mode, Refresh Showtime files.
- **Aux N intensity** faders (0–100%) appear for auxiliary ports configured as DMX Output. Adjusting a fader takes priority over live intensity for that auxiliary output without changing pixel brightness or playback mode. Values reflect the currently controlling intensity. The integration detects newly enabled DMX outputs while polling; previously added faders become unavailable when their port is changed to input or disabled.
- The device Sensors section shows temperature, CPU usage, input/output frame rate, input bank voltages, and supported per-output currents, voltages and power status. Operating mode and playback status remain diagnostic sensors.
- Binary sensors: playback error and playback paused.
- Status and measurements refresh every 10 seconds; the file list refreshes every 60 seconds. Commands request an immediate refresh. Disconnected controllers become unavailable and polling retries automatically.

Blank blanks the controller outputs; it does not remove electrical power. Live Data restores configured streaming input. Pause/Resume require an applicable file playback, and Previous/Next require a playlist; invalid commands return a controller error. Restart current mode can also restart recording if recording is active. The API's `Stop` only exits transient modes and is deliberately not presented as a universal stop button.

### Light behaviour

The light controls the **pixel outputs together**, not individual pixel ports or auxiliary DMX outputs. Its brightness is the effective master scaling factor, not a measurement of emitted light. Live input can contain black pixels even when the light reports on.

Turning the light off sets programmed intensity to zero and keeps playback running. Turning it on restores the last non-zero brightness remembered during this HA session (255 after a reload if no prior value is known). Selecting a colour replaces the current scene/live mode with a continuous solid colour. The separate Blank button enters a blank playback mode; a light On without a brightness or colour value after Blank starts white solid-colour playback. A brightness-only command preserves even a blank mode.

RGB pixels expose an RGB picker; RGBW pixels expose RGBW. RGBWX pixels expose RGBW and preserve the X channel from an existing solid colour, or use X=0 when switching from other modes. X is not assumed to be warm/cold white. Palette presets preserve all five channels and their original 8/16-bit values. The picker sends 8-bit HA colour values scaled to 16-bit; arbitrary 16-bit picker precision and separate X editing are not exposed.

Transitions are specified in seconds using standard HA light actions and sent in milliseconds. A colour-and-brightness action sends colour playback followed by intensity; these commands are serialized with other actions and polling. They are not an atomic controller transaction. A failure refreshes state to reflect any partially applied change. Status updates reflect controller polling rather than optimistic animation in HA.

Light and palette selection never write controller configuration. Palette colours are shown as Preset 1 through Preset 12 because the API stores values without names; the selector's `colours_16bit` attribute lists the values. Palette selection can interrupt recorded playback but cannot recolour the recorded scene itself.

On upgrading from an earlier version, replace the integration directory with the new version and restart HA. Existing device/entity IDs remain stable; new controls are added automatically. The setup user labels are Administrator and Operator; the API values remain `admin` and `oper`, so existing entries need no migration. Previously customised entity names remain as you set them.

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

Dim the running scene without replacing it:

```yaml
action: light.turn_on
target:
  entity_id: light.garden_pixlite_pixels
data:
  brightness_pct: 40
  transition: 2
```

Switch to a solid colour:

```yaml
action: light.turn_on
target:
  entity_id: light.garden_pixlite_pixels
data:
  rgb_color: [255, 80, 0]
  brightness_pct: 60
  transition: 1
```

## Showtime playlists

Playlists already stored as `.pl` files on the controller are supported in three places:

- **Showtime playlist** is a playlist-only dropdown. Selecting a playlist starts it immediately and repeats continuously. The original Showtime file selector remains available for existing automations.
- **Showtime playlist player** is a Home Assistant media player entity with a browser for stored playlists, Play/Pause and Previous/Next controls. It represents lighting playback, not audio, and has no volume control.
- **Playlist item**, **Playlist item type**, and **Playlist item file** sensors expose the current item. The player also has attributes for the item colour, elapsed playback seconds, repeat count and playback error code. Item position is reported exactly as supplied by the controller. The item filename is unknown for colour/blank/freeze items.

The player follows playlists started externally in Showtime too. Status refreshes every 10 seconds; the file browser refreshes every 60 seconds or using Refresh Showtime files. A missing SD card produces an empty browser. It may take the next status poll for the controller to report the first playlist item after starting playback.

Play resumes an active playlist; use the browser or dropdown to start one. Previous/Next navigate items within that playlist. No seek, shuffle, queue editing, playlist creation/uploads, or synchronized multi-controller playback is exposed. Use Blank or Live Data to leave playlist playback. A playlist error is represented by an idle player plus the existing Playback error binary sensor and error-code attribute.

For a finite number of repeats and a fade into the playlist, use this action with your actual player entity and filename:

```yaml
action: media_player.play_media
target:
  entity_id: media_player.garden_pixlite_showtime_playlist_player
data:
  media_content_type: advatek_pixlite
  media_content_id: "Evening.pl"
  extra:
    repeat_count: 1
    transition: 2
```

`repeat_count` accepts 0–65535; 0 (the default) loops forever. `transition` is the entry fade in seconds; it does not replace per-item fades authored in Showtime. The API does not allow a duration limit for playlist playback. When a finite playlist completes, the controller handles its normal transient-mode return behaviour. This integration does not promise to resume an arbitrary interrupted playlist at its former position.

## Transport and scope

All traffic stays on the local network. The API authenticates with Base64URL(SHA256(password)) query parameters, not HTTP Basic Auth. HTTP sends that reusable credential hash without encryption; use a trusted local network or configure HTTPS with the Advatek CA trusted by the HA environment. Certificate checking is never disabled. Credentials are stored in Home Assistant's config entry storage, and should be protected along with backups. Client errors intentionally omit request URLs.

This implementation uses HTTP polling; Advatek recommends WebSockets for push updates, which is a future improvement. No automatic network discovery, firmware updates, scene creation/uploads, pixel mapping changes, per-pixel streaming, or physical-controller configuration changes are included. Scenes/playlists must already exist on the controller. Adding/reloading the integration only reads data; output changes require an explicit entity action.

## Validation

`tests/test_api.py` runs the actual aiohttp client against a local HTTP simulator. It checks authentication encoding, version gating, endpoint/message formatting, serialization, file enumeration, result-less responses, and HTTP/API failures. `tests/test_controls.py` tests light/palette/priority behaviour and compound-command handling using lightweight HA interface doubles. These tests do not boot Home Assistant or substitute for hardware testing.

```sh
python -m pip install aiohttp pytest pytest-asyncio
python -m pytest tests -q
python -m compileall -q custom_components
```

Before relying on automations, test one controller: add it, compare readings with its UI, start a known scene, dim it, turn the light off/on, pick a solid colour and palette preset, check live intensity priority, pause/resume, blackout, restore live mode, unplug/reconnect the network, and test a second controller independently. Test missing SD media, credential changes and DHCP changes as well. These changes have not yet been tested on physical hardware or in a running HA instance.

## References

Implemented from the supplied **PixLite Mk3 API v1.9, V20260617**, especially sections 4, 6, 7.2, 7.7-7.9, 7.13-7.15. The PDF is not redistributed.

Home Assistant developer references: [config flows](https://contributors.home-assistant.io/core/integrations/config-flow/), [coordinated polling](https://contributors.home-assistant.io/core/integrations/fetching-data/), and [select entities](https://contributors.home-assistant.io/core/entities/select/).
