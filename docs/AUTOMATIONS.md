<!-- Copyright 2026 Gabriele Pennacchia -->
# Automations

Maintained by **Gabriele Pennacchia**.

Use the import links in the README, or open **Settings → Automations & scenes →
Blueprints → Import blueprint** and paste the GitHub URL of the YAML file.
HACS installs the integration; blueprints are imported separately. After importing,
choose **Create automation**, select your own entities and save.

## Temperature-based speed

Choose the MF10 fan, an external temperature sensor and an **input_boolean** helper
created under **Settings → Devices & services → Helpers → Toggle**. Turn on the
helper to enable speed adjustments. With the default thresholds, 24 °C requests
20%, 27 °C requests 60%, and 30 °C requests 100%. Values outside the thresholds
are clamped. Fahrenheit sensor readings are converted to Celsius.

The blueprint checks once per minute, on enabling the helper and when the fan
starts. It changes speed in the MF10's 10% steps and selects Manual mode. It does
not start a stopped fan. Missing readings, unknown units, disabled helpers or
reversed thresholds produce no command. Disable the helper before using the
night fade or choosing an automatic preset in Dreamehome.

## Switch off after absence

Choose a binary presence sensor where **on means occupied**, and an absence
duration. The wait starts when the room becomes empty or the fan is started in
an empty room. A return, an unavailable presence sensor or stopping the fan
cancels the wait. Turning the fan off is the only command this blueprint sends.

Restarting Home Assistant or reloading automations begins a fresh wait if the
room is still empty and the fan is on. Time while Home Assistant is stopped is
not counted. Select a presence sensor suitable for the room; a motion sensor
that clears while somebody sits still may switch the fan off unexpectedly.

## Gradual night speed

Choose a start time, an interval and whether to switch off at the end. The fan
must already be running in Manual mode. For example, 40% with a five-minute
interval becomes 30% after five minutes, 20% after ten and 10% after fifteen.
With final switch-off enabled, it stops after another interval at 10%.

Turning off the fan, a different reported speed, a preset change or loss of
availability cancels the fade. Restarting Home Assistant or reloading automations
also cancels it; it is not resumed automatically. Changes through the Dreamehome
app can only be detected when the cloud reports them. Do not run another speed
automation at the same time.

## Native timer and runtime sensors

The **Auto-off timer** number is a device command, independent of these blueprints.
Use 0 to cancel, or a whole number from 1 to 8 hours. Setting it never starts the
fan. The displayed value is reported by the device, not a locally calculated
minute-by-minute countdown.

The two operating-hours sensors can be used in history charts and automations.
They measure observed runtime since setup and today, in hours. They preserve
their totals across restarts, omit unobserved gaps, and are estimates rather than
a device lifetime counter. The `tracking_started_at` attribute records when
observation began; the daily sensor also includes its local `date`.
