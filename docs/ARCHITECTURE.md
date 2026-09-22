<!-- Copyright 2026 Gabriele Pennacchia -->
# Architecture

Flux uses native asynchronous Python because Home Assistant already owns the
event loop, HTTP connection pool, entity lifecycle and configuration storage.
There is no sidecar, subprocess or extra runtime to keep running.

The `api` package has no Home Assistant dependency. It handles the cloud session,
device bindings, validated MF10 commands and immutable snapshots. A coordinator
serializes operations for each fan and shares the result with all six entities.
Multiple fans with the same credentials share authentication and device discovery.

Every normal poll reads the nine known properties in one request. Device binding
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
available and off. An unreachable cloud makes all entities unavailable. An absent
online flag produces an unknown connectivity state.

Device names and firmware follow cloud binding metadata. Registry updates preserve
Home Assistant's user-supplied device name, entity IDs and other registry metadata.
Diagnostics record per-fan cloud update times and failures, plus command durations
and outcomes. Command durations exclude queueing; counters live in memory and reset
on reload. Device/account names and identifiers remain excluded from diagnostics.

The MF10 power action always includes a boolean input. There is deliberately no
generic RPC/action service: unknown actions are not part of the supported API.
Property writes are limited to known writable identifiers and allowed values.

Maintained by **Gabriele Pennacchia**.
