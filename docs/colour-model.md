# Colour support in Home Assistant

The controller's commissioned pixel selection determines its RGB, RGBW or RGBWX colour type. Home Assistant must read `config.pix.colorType`; it must not select a different pixel type or write controller configuration to expose a colour picker.

| Controller selection | Current Home Assistant light | Coverage |
| --- | --- | --- |
| RGB | `ColorMode.RGB`, three-channel picker | RGB values, master brightness and transitions are implemented. |
| RGBW | `ColorMode.RGBW`, four-channel picker, optional raw W number | RGB/W picker values plus independent 16-bit W editing. |
| RGBWX | `ColorMode.RGBW`, four-channel picker, optional raw W and X numbers | The picker retains an existing solid colour's X. Starting colour playback from another mode uses X=0. Independent W/X edits preserve the remaining channels and master intensity. |
| Missing or unsupported type | Brightness-only mode | No colour write is permitted. Presets and blank-to-colour restoration also require recognized configuration. |
| RGBWX commissioned as RGB+CCT | Raw W/X only | Native `RGBWW` and CCT conversion are not implemented. White-channel meanings and order still require verification. |

Enable the **Solid colour W** and **Solid colour X** entities in entity settings. They are disabled by default and created only for applicable channel types. Their range is 0 to 65535 with step 1. They become unavailable outside valid top-level solid-colour playback, after a poll failure, or when the configured channel disappears. They do not interrupt scenes, playlists or live input. Select a solid colour first. Raw channel changes use an immediate transition and leave master intensity untouched, including intensity zero.

The picker uses Home Assistant's 8-bit channel values scaled to the API's 16-bit range. Palette recall preserves the complete configured channel vector and source resolution. Picker and palette actions start solid-colour playback. Brightness-only commands preserve the current scene, playlist or live mode. A bare On after Blank starts RGB white with any W/X channels explicitly zeroed. These are software properties, not physical light-output measurements.

Every colour action rereads configuration and status while holding the command lock, then validates its channels before writing. Concurrent W/X changes use the latest controller status rather than a shared stale snapshot. Invalid current RGBWX solid colour blocks picker changes because X cannot safely be retained. Invalid palette vectors are rejected. These checks do not fix the controller identity issue R1 in PR #1. They cannot prevent a controller-side configuration change between read and write, because these API requests are not an atomic conditional colour transaction.

The API reference, *PixLite Mk3 API v1.9*, Advatek Lighting, V20260617 (17 June 2026), Table 46 on page 79, defines playback array order as red, green, blue, White, X. It does not establish X as warm or cold white. Home Assistant's [light entity contract](https://contributors.home-assistant.io/core/entities/light/) defines `rgbww_color` as `(red, green, blue, cold_white, warm_white)`. The commissioned LED profile or equivalent evidence must establish whether W/X have those meanings and their order. Do not infer white-channel ordering or a Kelvin range from RGBWX. The [number entity contract](https://contributors.home-assistant.io/core/entities/number/) provides the raw channel controls.

The Companion implementation uses raw R/G/B/W/X values, with controls determined by the controller's colour type. Its reported controller readbacks are not Home Assistant entity, service-routing or CCT-conversion evidence.

## Verification and remaining requirements

Local protocol tests cover configured RGB/RGBW/RGBWX modes, 8/16-bit conversion, configured vector lengths, transitions, palette recall, X retention, raw W/X preservation, invalid values, mode changes, missing/unsupported configuration and concurrent edits. Separate real Home Assistant service tests cover service conversion, channel writes, registry state and unknown-type rejection against an in-memory controller.

Physical colour and CCT remain unverified. Confirm controller readback and emitted output on approved hardware, both possible warm/cold orderings, actual Kelvin limits and the commissioned profile before adding native CCT conversion. R1 through R5 in PR #1 and the other Core-readiness requirements remain open. Command acceptance or readback alone does not prove emitted colour or CCT.

The initial Core candidate contains only sensors. Its first upstream payload includes no light or colour platform. Colour controls require a separate reviewed contribution after the mapping and verification work is complete.
