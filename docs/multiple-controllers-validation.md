# Concurrent A4-S and E16-S validation

Validation date: 23 October 2026. Runtime: Python 3.14.2, Home Assistant 2026.10.2 on Windows. Both controllers were connected to the same /24 network, with the workstation using WiFi at 192.168.1.75.

| Controller | Address | Firmware | Observed configuration | HA entities |
| --- | --- | --- | --- | --- |
| PixLite A4-S Mk3 | 192.168.1.84 | 3.15.0 | Four pixel ports, RGBWX, one auxiliary DMX output, power monitoring | 36 |
| PixLite E16-S Mk3 | 192.168.1.50 | 3.15.0 | Sixteen pixel ports, RGB, one auxiliary DMX output, no output-power monitoring | 27 |

Both devices advertised API v1.0 through v1.9. Authenticated API reads confirmed their MACs and capabilities. Actual HA discovery flows created two independent config entries, clients and coordinators. Their entity IDs were disjoint across all seven platforms: light, select, number, button, sensor, binary sensor and media player.

## Physical checks

| Check | Observed result |
| --- | --- |
| Two discovery clients at once | Three concurrent pairs, six completed scans. Each independently found both controllers, used separate UDP ports and returned no conflicts. |
| Setup and monitoring together | Both real config entries loaded and completed three concurrent polling rounds. One shared ADAR manager owned both entry IDs. |
| Pixel brightness and on/off | Different brightness values, 51 and 102, reached the intended controllers. Brightness preserved the existing playback/live mode. Off and On completed on both. |
| Colour and palette | A4 RGBWX and E16 RGB commands were accepted. API colour readbacks matched the requested channel values; distinct palette selections returned the expected colours. |
| Priority and auxiliary intensity | Different pixel priorities and auxiliary intensity factors, 64 and 191, were read back from the intended controllers. |
| Playback buttons | Blank, Freeze, Live Data, Pause, Play, Previous, Next, Restart current mode and Refresh Showtime files completed on both. |
| Files and playlists | A stored A4 scene and valid playlists on both devices were selected. Each media browser listed its own controller's playlist files. |
| Media player | Play media, Pause, Play, Next and Previous completed on both after the refresh fix below. Pause/Play state was read back. |
| Missing media | The E16's existing Evening Playlist referenced absent scenes and reported error 16. Only its playback-error entity turned on, and its player reported idle. Selecting its valid New Playlist cleared the error. |
| Reload and unload | Reloading the A4 preserved its entity IDs, the E16 coordinator and the shared scanner task. Unloading the A4 left E16 polling operational. Unloading the final entry stopped discovery. |
| Restoration | The A4's original Evening Playlist and the E16's live mode were restored. Programmed pixel/auxiliary intensity factors returned to 255 with Low priority on both, verified by API readback. |

The final live run completed 27 stages. The test harness checked the target MAC before every output request and allowed only the integration's operating controls. IP configuration, recovery, firmware, controller reboot, file uploads and file deletion were excluded. Original modes, playback parameters, programmed intensities and priorities were recorded before output testing. The API cannot restore the A4's exact prior playlist item/time; restoring its playlist restarted playback.

The E16 normalized solid-colour status to a four-value array with a zero unused channel, including after a three-value RGB command. Colour comparisons preserve the requested active channels and account for zero padding. This does not imply an additional active white channel in its RGB configuration.

## Refresh bug found and corrected

The first live run reproduced an existing state-timing defect. The E16 began in live mode. Starting a playlist succeeded on the controller, but an immediate HA media-player Pause failed with `Select a Showtime playlist first` because its coordinator still held the previous live state.

Home Assistant's default requested-refresh debounce has a ten-second cooldown. `PixLiteCoordinator.commands` used that requested refresh after commands, allowing a dependent action to see old state. Command completion and error reconciliation now await an immediate coordinator refresh. The regression test starts the cooldown, plays a playlist from live mode, then pauses immediately. It failed before the change and passes after it. The subsequent physical run also passed the same sequence.

## Automated isolation checks

`tests/test_multiple_instances.py` loads two simulated controllers through actual HA config managers, registries, platforms, services and coordinators. It tests identical friendly names, independent identities and measurements, concurrent commands, per-controller file lists, a blocked command, an offline controller and recovery, command rejection, reload/unload in either order, discovery-scan serialization and separate setup flows. These tests isolate failures without disconnecting or reconfiguring the physical devices.

The final local suite passed 187 tests, including the 57 original tests. Overall line coverage was 97.87% (872/891 statements); the ADAR protocol, manager, ADAR flow and config flow each had 100% line coverage. The run reported 47 dependency warnings and no unhandled task or unclosed-session errors. Line coverage is not exhaustive hardware qualification.

The original controller-substitution risk from PR #1 remains open. The live harness's extra identity check is test instrumentation, not a new protection in the integration. This work does not establish Linux/container behaviour, other firmware/model combinations, unattended endurance, calibrated emitted colours or physical pixel output quality. Core submission and Gold qualification remain separate requirements.
