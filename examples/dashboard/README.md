# Optional Advatek dashboard

An example dashboard for one A4-S Mk3 and one E16-S Mk3, with an optional Advatek theme. It uses Home Assistant's built-in cards and requires no custom frontend plugins. Installing the integration does not install or select this theme.

## Appearance

`advatek-theme.yaml` uses Advatek orange `#F15A2C`, charcoal `#353436` and white from the corporate palette in *External Brand Guidelines*, pages 9 and 10. Additional orange tones and neutral surfaces are UI adaptations for contrast, not additional official brand colours. Both light and dark modes are included. Error, warning and success colours retain Home Assistant's meanings, and the colour picker retains its full spectrum.

The theme includes the primary design-token palette used by newer controls as well as classic colour variables. It was loaded successfully in Home Assistant 2026.10.2. Retest after frontend updates because theme variables can change.

## Install

1. Copy `advatek-theme.yaml` to your Home Assistant configuration folder as `themes/advatek.yaml`.
2. Add the following under the existing `frontend` section of `configuration.yaml`. Keep other frontend settings and do not duplicate that section:

   ```yaml
   frontend:
     themes: !include_dir_merge_named themes
   ```

3. Run **Frontend: Reload themes**, or restart Home Assistant.
4. Create a separate dashboard and paste `pixlite.yaml` into its raw configuration editor. Alternatively, register it as a YAML dashboard using the example below. Replace entity IDs with those shown on your controllers' device pages. Remove blocks for models or outputs you do not have.
5. Each view selects `theme: Advatek`. To apply the same appearance to dialogs and the surrounding interface, optionally select **Advatek** in your own user profile. Users can keep their existing theme.

```yaml
lovelace:
  dashboards:
    pixlite-controls:
      mode: yaml
      title: PixLite
      icon: mdi:led-strip-variant
      show_in_sidebar: true
      filename: pixlite.yaml
```

The YAML-dashboard example assumes `pixlite.yaml` is beside `configuration.yaml`. Merge it into an existing `lovelace.dashboards` mapping if one is already configured.

## Graphical monitoring

- CPU usage uses a gauge with its natural 0 to 100 percent range.
- Temperature, input/output frame rates, voltage and output currents use sensor cards with one-hour line graphs. These are measured values, not percentages of an assumed hardware limit.
- Output power status uses compact tiles alongside the per-output measurements.
- No temperature, voltage or current warning thresholds are invented. Use verified limits for your exact controller and installation before adding severity bands.

Enable the disabled diagnostic entities used by the example, including CPU, frame rates and per-output current, from each controller's entity list. Entity IDs depend on the controller nickname and existing registry, so the IDs in this file are examples.

Graphs require Home Assistant's Recorder and History integrations, with these entities included in recording. They are normally present with `default_config`. If you manage a minimal configuration, add `recorder:` and `history:` or merge the necessary entity filters into your existing settings. Do not replace existing recording or retention policies just for this dashboard. A new installation has no earlier history; graphs fill only as real readings arrive. Unavailable controllers remain visibly unavailable.

Validation: YAML parsing, successful theme loading, contrast checks for the principal text/surface combinations, and desktop rendering of the built-in cards on HA 2026.10.2. Populated graphical screenshots and mobile visual checks remain pending because the test controllers became unreachable. No controller configuration changes are required for this dashboard.

References: [themes](https://www.home-assistant.io/integrations/frontend/#defining-themes), [view themes](https://www.home-assistant.io/dashboards/views/#theme), [gauge cards](https://www.home-assistant.io/dashboards/gauge/) and [sensor cards](https://www.home-assistant.io/dashboards/sensor/).
