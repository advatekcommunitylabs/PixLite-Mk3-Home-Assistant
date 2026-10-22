# Colour support in Home Assistant

The controller's commissioned pixel selection determines its RGB, RGBW or RGBWX colour type. Home Assistant must read `config.pix.colorType`; it must not select a different pixel type or write controller configuration to expose a colour picker.

| Controller selection | Current Home Assistant light | Coverage |
| --- | --- | --- |
| RGB | `ColorMode.RGB`, three-channel picker | RGB values, master brightness and transitions are implemented. |
| RGBW | `ColorMode.RGBW`, four-channel picker | RGB and W values, master brightness and transitions are implemented. |
| RGBWX | `ColorMode.RGBW`, four-channel picker | An existing solid colour's X value is retained. Starting colour playback from another mode uses X=0. Palette recall retains all five channels. Independent X editing is absent. |
| RGBWX commissioned as RGB+CCT | No native CCT or `RGBWW` implementation | Not full RGBCCT support. White-channel order and actual temperature limits must be established before adding this behavior. |

The picker uses Home Assistant's 8-bit channel values scaled to the API's 16-bit range. Palette recall preserves the complete channel vector and source resolution. Colour commands start solid-colour playback; brightness-only commands preserve the current scene, playlist or live mode. These are software properties, not physical light-output measurements.

Home Assistant's [light entity contract](https://github.com/home-assistant/developers.home-assistant/blob/master/docs/core/entity/light.md) defines `rgbww_color` as `(red, green, blue, cold_white, warm_white)`. The commissioned LED profile or equivalent evidence must establish whether W/X have those meanings and their order. Do not infer white-channel ordering or a Kelvin range from the string RGBWX alone.

The Companion implementation uses raw R/G/B/W/X values, with controls determined by the controller's colour type. Its reported controller readbacks are not Home Assistant entity, service-routing or CCT-conversion evidence.

## Follow-up requirements

- Keep controller configuration authoritative. Block colour commands if it is missing or unrecognized. The current fallback to RGB remains a review issue; this preparation does not fix it.
- Expose all five values for commissioned RGBWX installations. Separately decide whether to provide raw W/X controls, mapped native `RGBWW`, or both. Do not add another pixel-type selector.
- For RGB+CCT, verify W/X semantics, warm/cold ordering and physical Kelvin bounds before adding temperature conversion. Preserve R/G/B and brightness independently.
- Test both white-channel orderings, missing/unsupported configuration, RGB/RGBW/RGBWX capabilities, 8/16-bit conversion, transitions, palette recall, mode changes and X retention.
- Verify real Home Assistant service calls and state, then approved controller readback and physical output. Command acceptance or readback alone does not prove emitted colour or CCT.

The initial Core candidate contains only sensors. Its first upstream payload includes no light or colour platform. Colour controls require a separate reviewed contribution after the mapping and verification work is complete.
