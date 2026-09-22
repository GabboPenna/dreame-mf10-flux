<!-- Copyright 2026 Gabriele Pennacchia -->
# Dreame MF10 Flux

![Dreame MF10 Flux](https://raw.githubusercontent.com/GabboPenna/dreame-mf10-flux/main/docs/images/brand.png)

[![Validate](https://github.com/GabboPenna/dreame-mf10-flux/actions/workflows/validate.yml/badge.svg)](https://github.com/GabboPenna/dreame-mf10-flux/actions/workflows/validate.yml)
[![Release](https://img.shields.io/github/v/release/GabboPenna/dreame-mf10-flux)](https://github.com/GabboPenna/dreame-mf10-flux/releases)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://github.com/GabboPenna/dreame-mf10-flux/blob/main/LICENSE)

Native Home Assistant controls for the **Dreame Bladeless Fan MF10**.

Maintained by **Gabriele Pennacchia**.

Flux connects to your Dreamehome account and presents the MF10 as a fan, with
temperature, child lock, base rotation, blade oscillation and cloud connectivity.
It uses asynchronous requests, one shared account session and batched state reads.

## Requirements

- Home Assistant **2026.9 or newer**.
- A Dreame MF10, model `dreame.fan.u2519`, linked to your Dreamehome account.
- Internet access to the Dreame cloud. Local-only control is not supported.
- The implemented property layout targets firmware 1043 and later. Live validation
  uses firmware **1.8.30_1047** in the **EU** region. Other versions and regions
  need hardware confirmation; they are not implied by the region selector.

## Install with HACS

[Open the repository in HACS](https://my.home-assistant.io/redirect/hacs_repository/?owner=GabboPenna&repository=dreame-mf10-flux&category=integration)

1. Open HACS and choose **Custom repositories**.
2. Add `https://github.com/GabboPenna/dreame-mf10-flux` as an **Integration**.
3. Download **Dreame MF10 Flux** and restart Home Assistant.
4. Open **Settings → Devices & services → Add integration → Dreame MF10 Flux**.
5. Enter your Dreamehome account and account region, then select your fan.

For manual installation, copy `custom_components/dreame_mf10_flux` into your
Home Assistant `custom_components` directory and restart Home Assistant.

## Controls

| Entity | Function |
| --- | --- |
| Fan | Power, ten speed levels, AI / Powerful / Sleep / Manual / Natural presets |
| Temperature | Ambient temperature, converted to your preferred unit by Home Assistant |
| Child lock | Enable or disable the controls on the device |
| Base rotation | Enable or disable base rotation |
| Blade oscillation | Off, left, right, both, synchronized, staggered |
| Cloud connectivity | Online state reported by Dreame, separate from fan power |

Setting a speed selects Manual mode. The fan's oscillation toggle selects both
blades or stops them; use the blade-oscillation selector for the full set of modes.
Automation values remain stable when you change the Home Assistant language.
If a turn-on action specifies both a speed and an automatic preset, the preset
takes priority and chooses its own speed.

Fans use their names from Dreamehome, including later name changes. A name you
set manually in Home Assistant takes priority. Existing entity IDs stay unchanged.

## Languages

Setup, options, entity names, preset labels and errors include complete locale
files for English, Italian, German, French, Spanish, Portuguese, Brazilian
Portuguese, Dutch, Polish, Japanese, Simplified Chinese and Traditional Chinese.
Home Assistant falls back to English for other languages, so changing your UI
language does not prevent setup or operation. Native-language review and further
translations are welcome; this is not a claim of human-verified coverage of every
language. Documentation is maintained in English.

For an existing fan setup, see [Keeping existing automations](https://github.com/GabboPenna/dreame-mf10-flux/blob/main/docs/MIGRATION.md).

## Updates and performance

All entities share one property request every 30 seconds. You can change the
interval from 10 to 300 seconds in the integration options. Account device status
is cached for at most 60 seconds across fans on the same account.

A command groups related property changes and checks the reported values against
the requested state. It normally needs one confirmation read; if the cloud still
reports an older state, Flux makes up to two additional reads, waiting 0.5 and
1 second respectively. A mismatch reports a command error while keeping the
actual state visible. Rapid commands are processed in order, including deciding
whether a speed change needs to turn the fan back on.
Synchronized and staggered blade movement use two ordered writes because the
firmware resets those flags when blade movement changes.
Unchanged snapshots do not trigger extra state updates. Token renewal is shared
across simultaneous requests, HTTP connections are reused, and all network calls
have time limits. Read operations may retry once; an uncertain write is never
automatically repeated. After an uncertain or partially accepted write, Flux
tries one state refresh. Authentication failures and rate limits stop follow-up
reads; rate-limit responses pause further cloud requests.

Cloud latency, cloud caches and firmware behavior still affect update times.
The connectivity sensor reflects the cloud's knowledge, not a local network probe.

## Privacy and troubleshooting

Credentials are stored in Home Assistant's configuration entry and may be included
in backups. Protect access to your Home Assistant configuration and backups.
Flux does not add a separate encryption layer. Session tokens stay in memory.

Diagnostics contain only operational state, firmware, region and timing counters.
They include the last successful cloud update in UTC, consecutive update failures,
command duration and outcome, and total/consecutive command failures. Command
timings include writes and confirmation, excluding time waiting for an earlier
command. Counters reset when the integration reloads; request counts cover the
shared account, while command and update counters belong to each fan.
They omit account names, passwords, tokens, device identifiers and MAC addresses.
There is no analytics or telemetry service.

If authentication expires, Home Assistant offers reauthentication. Signing in
again also updates other configured fans with the same account and region, but
only if the cloud confirms they belong to that account. Disabled entries remain
disabled; other accounts and regions are unchanged. If no fan is
found, check the account region and that the device is linked in Dreamehome.
Only MF10 devices are offered during setup. Cloud outages are retried through
Home Assistant; do not delete and recreate the integration to recover a session.

## Development

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[dev]'
python -m unittest discover -s tests -v
ruff check .
```

Protocol tests use fake devices and responses. Home Assistant tests run separately
with a temporary configuration. They never use a live account or operate hardware.

Read the [architecture](https://github.com/GabboPenna/dreame-mf10-flux/blob/main/docs/ARCHITECTURE.md)
and [contribution guide](https://github.com/GabboPenna/dreame-mf10-flux/blob/main/CONTRIBUTING.md).

## License

MIT. Copyright © 2026 **Gabriele Pennacchia**.

This is an unofficial integration, not affiliated with or endorsed by Dreame.
Dreame and Dreamehome are trademarks of their respective owners.
