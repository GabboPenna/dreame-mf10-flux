<!-- Copyright 2026 Gabriele Pennacchia -->
# Changelog

## 1.1.0 — 2026-09-23

- Add a display switch and native auto-off timer with whole-hour settings from
  0 to 8. Zero cancels; setting the timer does not start the fan. Both controls
  use firmware 1047 properties verified by read/write/restore checks.
- Keep core controls usable when firmware rejects the optional property batch.
  Missing optional values make only their own controls unavailable.
- Add daily and total observed operating-hour sensors with persistent storage,
  local-midnight reset, daylight-saving handling and no extrapolation through
  cloud outages or Home Assistant downtime.
- Include three optional automation blueprints: external-temperature speed,
  absence shutoff and gradual night speed with cancellation on manual changes.
- Extend all twelve UI translations and document automation setup and limitations.
- Cover controls, fallback behavior, runtime persistence and blueprint execution
  with 80 automated tests against the protocol and Home Assistant 2026.9.3.
- Blade realignment remains unavailable until its app command is captured and
  verified. No unverified action or replacement oscillation sequence is exposed.

## 1.0.2 — 2026-09-23

- Fix a queued speed change leaving the fan off after an in-flight power-off command.
- Compare reported state with the requested command and allow two bounded follow-up
  reads for delayed cloud updates. Report unconfirmed commands without replaying writes.
- Refresh actual state after uncertain or partially accepted commands; preserve
  authentication recovery and cloud request cooldowns.
- Use Dreamehome fan names, including later changes, while preserving Home Assistant
  name overrides and existing entity IDs.
- Reauthenticate verified fans on the same account and region together, without
  duplicate reloads or enabling disabled entries.
- Add last successful update time, consecutive update failures, command duration,
  outcome and failure counters to identifier-free diagnostics.
- Let an automatic preset take priority when a turn-on action also supplies a speed.
- Add 16 Home Assistant regression tests; all 60 automated tests pass. Validate
  commands on an EU MF10 running firmware 1.8.30_1047 and restore its configuration.

## 1.0.1 — 2026-09-22

- Redraw MF10 FLUX lettering using the supplied Dreame wordmark's shapes and
  stroke weight, replacing the system font in the logos and icon badge.
- Regenerate light/dark and standard/high-resolution assets and the README image.
- Make artwork generation independent of installed system fonts. This is custom
  matching lettering, not an official Dreame font.

## 1.0.0 — 2026-09-22

- Native asynchronous Home Assistant integration for the Dreame MF10.
- Power, ten speeds, five presets, temperature, child lock, base rotation,
  six blade-oscillation combinations and cloud connectivity.
- Shared account sessions, single-flight token renewal, batched polling,
  serialized commands, bounded timeouts and cloud rate-limit handling.
- Ordered synchronization writes validated on firmware 1.8.30_1047.
- Setup, multiple-device selection, reauthentication and configurable polling.
- Diagnostics that omit credentials, tokens and device identifiers.
- Twelve complete UI locale files, English fallback and English documentation.
- MF10 Flux branding, HACS packaging and automated validation.
- 26 protocol/localization tests and 18 tests using real Home Assistant classes.
- Live validation on Home Assistant 2026.9.3 in the EU region: power, speed,
  all five presets, both switches and all six oscillation settings. Initial
  device settings were restored after testing. Other regions remain unverified.

Maintained by **Gabriele Pennacchia**.
