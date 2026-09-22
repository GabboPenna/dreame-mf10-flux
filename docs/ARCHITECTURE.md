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
metadata refreshes at most once a minute. Commands send the necessary property
batch and/or explicit power action, then read one snapshot. Cloud acknowledgement
does not guarantee immediate physical convergence; a later poll can still change
the reported state.

Synchronized and staggered oscillation require two ordered writes: blade movement
with both flags cleared, then the selected flag. Live firmware 1047 testing showed
that writing the movement after the flag can acknowledge success while resetting
that flag. A regression test emulates this firmware behavior.

Authentication is single-flight, including simultaneous requests rejected with
an expired token. A refresh token is preferred; rejected refresh credentials fall
back to the account password. Authentication failure opens the Home Assistant
reauthentication flow. No credentials or raw cloud responses are logged.

Reads can retry once after a transport failure. Writes are only resubmitted after
an explicit authentication rejection, never after a timeout or server failure.
Cloud rate limits pause the shared account transport. Requests have a 15-second
total timeout and an 8-second connection timeout.

Availability is based on successful cloud communication and the binding's online
flag. A disconnected fan disables controls but keeps its connectivity sensor
available and off. An unreachable cloud makes all entities unavailable. An absent
online flag produces an unknown connectivity state.

The MF10 power action always includes a boolean input. There is deliberately no
generic RPC/action service: unknown actions are not part of the supported API.
Property writes are limited to known writable identifiers and allowed values.

Maintained by **Gabriele Pennacchia**.
