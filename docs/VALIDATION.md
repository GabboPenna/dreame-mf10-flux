<!-- Copyright 2026 Gabriele Pennacchia -->
# Release validation

## Version 1.0.2

Tested on 2026-09-23 with Home Assistant 2026.9.3 and the same EU MF10 running
firmware 1.8.30_1047. Automated coverage comprises 26 protocol/localization tests
and 34 Home Assistant framework tests, using temporary configurations and fictional
accounts. The new cases cover queued power/speed commands, delayed or missing
confirmation, partial writes, authentication and rate limits, shared account
recovery, device-name overrides and diagnostic counters/redaction.

Live validation through the installed Home Assistant entities confirmed both
switches, all six oscillation settings, all five presets, power, manual speed and
automatic power-on when setting a nonzero speed. All 21 service commands completed
without command failures. The six existing entity IDs and their registry metadata
were preserved across the update.

The original power-off state, AI preset, base rotation, child lock and oscillation
were restored. AI recalculates its reported speed even while powered off, so speed
restoration is checked exactly only for Manual mode. Cloud-reported state is not
an independent measurement of airflow or movement. Multiple-account recovery is
covered with simulated accounts; no real account passwords were changed.

## Version 1.0.0

Version 1.0.0 was tested on 2026-09-22 with Home Assistant 2026.9.3, Python
3.14.6 and a Dreame MF10 running firmware 1.8.30_1047 in the EU region.

Automated coverage comprises 26 protocol/localization tests and 18 framework
tests. The protocol suite uses a real local HTTP server with fictional account
data. Framework tests run against Home Assistant with a temporary configuration.

Live tests used the installed Home Assistant entities to verify:

- Child lock and base rotation in both states.
- Every blade-oscillation option, including switching between synchronized and
  staggered movement.
- AI, Powerful, Sleep, Manual and Natural presets.
- Power on at speed 1, a change to speed 3 and power off.
- Temperature and cloud connectivity readings.
- Correct Italian names and successful setup after a Core restart.

Observed service-call completion times were approximately 0.45–0.81 seconds for
these tests, including the confirmation read. These are measurements from one
device and connection, not a latency guarantee or a benchmark against another
integration. Cloud acknowledgement and reported state do not independently
measure physical airflow or movement.

The initial power, stored speed, preset, lock, rotation and oscillation settings
were restored and checked after testing. A configuration backup was retained.

Other firmware versions and cloud regions require independent hardware testing.
Locale files are checked for matching keys; native-language review remains welcome.

Maintained by **Gabriele Pennacchia**.
