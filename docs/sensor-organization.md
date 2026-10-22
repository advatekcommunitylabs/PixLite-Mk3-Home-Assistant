# Sensor organization

The integration uses Home Assistant's device page and entity categories. All entities stay under one physical controller. Channel names identify the input bank or pixel output without inventing extra devices or custom dashboard sections.

| Group | Entities | Default for a new entry |
| --- | --- | --- |
| Playback | Mode | Enabled |
| Hardware diagnostics | Temperature, bank input voltage, output power status | Enabled |
| Performance diagnostics | CPU usage, input and output frame rates | Disabled, available to enable |
| Detailed output diagnostics | Per-output current and voltage | Disabled, available to enable |
| Playback details | Playback file and playlist item details | Disabled, available to enable; the existing player and selectors already expose playback controls |

These defaults apply when an entity is first registered. Existing entity IDs, enabled states and user names remain in Home Assistant's registry. Updating the integration does not force an existing user's configuration to the new defaults.

Descriptions define units, measurement state classes, categories, default enabled state, and translation keys. Repeated channels use translation placeholders such as `Output {channel} current`. Hardware capability fields determine which channel entities are created. A temporarily missing reading becomes unknown without removing the supported entity; a failed controller update makes its entities unavailable.

The pattern follows Home Assistant's [WLED sensor implementation](https://github.com/home-assistant/core/blob/2026.10.2/homeassistant/components/wled/sensor.py). WLED's device-specific values and controls are not copied: PixLite's bank/output measurements and controller playback remain the source of truth. Temperature, voltage, current, CPU and frame rate describe controller health, so their entity category is diagnostic. Diagnostic category and disabled-by-default status are independent.

Separate devices per output, automatic custom dashboards, new power/energy calculations, thresholds, extra measurements, and power-control commands are outside this change. They would require separate behavior and verification. A current reading is not an energy measurement, and an output status is not a command to switch power.
