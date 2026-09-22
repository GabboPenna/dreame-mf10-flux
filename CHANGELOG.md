<!-- Copyright 2026 Gabriele Pennacchia -->
# Changelog

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
