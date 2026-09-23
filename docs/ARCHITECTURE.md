<!-- Copyright 2026 Gabriele Pennacchia -->
# Architecture

Flux uses native asynchronous Python because Home Assistant already owns the
event loop, HTTP connection pool, entity lifecycle and configuration storage.
There is no sidecar, subprocess or extra runtime to keep running.

The `api` package has no Home Assistant dependency. It handles the cloud session,
device bindings, validated MF10 commands and immutable snapshots. A coordinator
serializes operations for each fan and shares the result with all eleven entities.
Multiple fans with the same credentials share authentication and device discovery.

Every normal poll reads twelve properties in one request. Pre-filter, display and
timer values are optional. If firmware rejects the complete batch, Flux first
tries the previous eleven-property group, preserving display and timer support.
If that also fails, it tries the nine core properties. A successful group is
cached until reload or a firmware change. Transport, authentication and rate-limit
errors stop fallback reads. Device binding
metadata refreshes at most once a minute. The device lock covers state-dependent
decisions, writes and confirmation, so a queued speed change sees the outcome of
an earlier power command. Commands check a fresh snapshot against the requested
values. A matching first snapshot completes immediately; stale or missing values
allow two extra snapshots after delays of 0.5 and 1 second. A remaining mismatch
raises a translated command error without marking a reachable cloud unavailable.
Only cloud-reported state is confirmed, not independently measured physical motion.

Synchronized and staggered oscillation require two ordered writes: blade movement
with both flags cleared, then the selected flag. Live firmware 1047 testing showed
that writing the movement after the flag can acknowledge success while resetting
that flag. A regression test emulates this firmware behavior.

Authentication is single-flight, including simultaneous requests rejected with
an expired token. A refresh token is preferred; rejected refresh credentials fall
back to the account password. Authentication failure opens the Home Assistant
reauthentication flow. Successful reauthentication updates verified device entries
with the same account email and region, clears their pending reauthentication
flows and reloads each enabled entry once. Changing account identity updates only
the initiating entry. No credentials or raw cloud responses are logged.

Reads can retry once after a transport failure. Writes are only resubmitted after
an explicit authentication rejection, never after a timeout or server failure.
An uncertain write triggers one best-effort snapshot to reconcile partial changes;
the service still reports the write error. Authentication failures and rate limits
skip reconciliation. A failed confirmation read uses the existing transport retry
policy without further coordinator retries.
Cloud rate limits pause the shared account transport. Requests have a 15-second
total timeout and an 8-second connection timeout.

Availability is based on successful cloud communication and the binding's online
flag. A disconnected fan disables controls but keeps its connectivity sensor
available and off. An unreachable cloud makes live entities unavailable; persisted
operating-hour totals remain readable. An absent
online flag produces an unknown connectivity state.

Device names and firmware follow cloud binding metadata. Registry updates preserve
Home Assistant's user-supplied device name, entity IDs and other registry metadata.
Diagnostics record per-fan cloud update times and failures, plus command durations
and outcomes. Command durations exclude queueing; counters live in memory and reset
on reload. Device/account names and identifiers remain excluded from diagnostics.

The MF10 power action always includes a boolean input. There is deliberately no
generic RPC/action service: unknown actions are not part of the supported API.
Property writes are limited to known writable identifiers and allowed values.

Display is property 6/12 (0 or 1); the native auto-off timer is 6/8 (hours, zero
cancels). Both were read, written and restored on firmware 1.8.30_1047. Timer
settings of 1 and 8 hours were confirmed; Flux accepts 0–8 in whole-hour steps.
No remaining-minutes field or blade-realignment command has been verified.
Blade realignment therefore has no entity yet; it needs a captured app command
and hardware validation before it can be exposed.

Pre-filter cleaning days use property 4/8, verified against the app's remaining
days on firmware 1.8.30_1047. The parser accepts whole days from 0 to 365 and rejects
missing, failed, negative or malformed readings. The duration sensor uses days
and the measurement state class; it is neither a cumulative total nor a locally
decremented countdown. The property is absent from the write allowlist.

Observed runtime uses monotonic elapsed time and UTC samples, splitting the daily
total at local midnight. Failed reads, offline states, clock jumps and gaps longer
than two polling intervals plus 30 seconds discard the open interval. A separate
midnight callback resets the daily value during outages. A Home Assistant Store
persists counters per entry; no time is inferred between shutdown and startup.
Runtime listeners update sensors even when the immutable fan snapshot is unchanged.

Blueprints remain separate from the integration lifecycle and send standard fan
services. Tests import them through Home Assistant's blueprint and automation
schemas and execute their actions against simulated entities and services.

Maintained by **Gabriele Pennacchia**.
