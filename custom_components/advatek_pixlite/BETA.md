# PixLite Mk3 beta installation and feedback

This custom integration connects Home Assistant to Advatek PixLite Mk3 controllers. It lets Home Assistant users monitor controller health and automate pixel brightness, colour and existing Showtime playback. Advatek Assistant and SHOWTime remain the tools for commissioning controllers and creating/managing show content.

## Install

1. Back up your Home Assistant configuration. This beta is not a Core integration or Marketplace listing.
2. Download `advatek_pixlite-0.4.1-beta.1.zip` and `SHA256SUMS-v0.4.1-beta.1.txt` from the same GitHub prerelease. Verify the ZIP SHA-256 before extraction.
3. Extract only `custom_components/advatek_pixlite` into your HA configuration directory. The resulting path is `/config/custom_components/advatek_pixlite/manifest.json`. Preserve your existing integration folder as a backup if upgrading; do not install two copies of the same domain.
4. Restart Home Assistant. Open Settings > Devices & services > Add integration > Advatek PixLite Mk3.
5. Enter the controller address, enabled Administrator or Operator user, and its existing password. Add each controller separately.
6. For Advatek HTTPS, choose HTTPS and enter the controller's Ethernet MAC from its label, independently of discovery or API output. The default port is 4443. HTTP defaults to 80. A port value of 0 clears an override and uses the selected protocol's default. Do not bypass a certificate or identity refusal.
7. The controller API address must be reachable from the Home Assistant host. For a simple local installation, use addresses in the same subnet. Discovery, IP changes and recovery are not provided by this beta.

The tested HA target is 2026.10.2. Newer/older versions and supported Linux deployments have not been qualified by this project. Prior physical tests used A4-S/E16-S firmware 3.15.0 on Windows with a private runtime cleanup correction that is not included here. Read the release limitations before testing.

## Controls

Selecting a scene, playlist, palette colour or picker colour can immediately change live output. The pixel light affects pixel outputs together, not individual ports. Brightness-only control preserves playback mode; colour selection switches to solid-colour playback. W/X are raw channels, not calibrated Kelvin controls. Blank does not disconnect electrical power. Existing scene/playlist files must already be on the controller; this integration does not upload media or edit commissioning settings.

Optional diagnostic sensors and raw W/X number entities can be enabled from entity settings. Existing custom entity names and registry IDs are retained when upgrading this integration. Refer to the source README for the complete controls and automation examples.

## Roll back or remove

Remove the integration entries from Settings > Devices & services to stop HA polling. To roll back, restore your preserved earlier integration folder and HA configuration backup, then restart HA. To uninstall, use HA's normal integration removal and file-management process. Removing this integration does not remove scene/playlist files or controller configuration.

## Report a finding

Use the GitHub issue tracker linked in the release. Include:

- Version 0.4.1-beta.1 and runtime base commit 8303f8f. The release tag also includes the beta version metadata, documentation and Apache 2.0 licence.
- HA/Python version, controller model and firmware, HTTP/HTTPS and whether one or several entries were loaded.
- Minimal steps, expected/actual behavior and relevant redacted errors.
- Whether a peer controller was affected and whether the issue concerns monitoring or an operating command.

Do not attach passwords, tokens, full configuration dumps or private network details. Visual colour observations are useful feedback, but are not calibrated optical/electrical qualification.

This guide and release review are AI-generated. Human maintainers remain responsible for review and support.
