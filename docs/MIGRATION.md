<!-- Copyright 2026 Gabriele Pennacchia -->
# Keeping existing automations

Flux uses the integration domain `dreame_mf10_flux`. Home Assistant treats it as
a separate integration. It does not automatically import another integration's
configuration or take ownership of its entities.

Before replacing any existing fan setup, create a Home Assistant backup and note
its entity IDs. Add Flux and verify that its state matches the device. Disable
the previous configuration entry before using Flux as the active controller.

To keep automations that target entity IDs, rename the disabled entities to free
their old IDs, then assign those IDs to the equivalent Flux entities in each
entity's settings. Copy any custom names, areas and labels. Device-based actions
and triggers may refer to internal registry IDs: review those separately.
Review dashboards and voice assistant exposure after the change.

Keep the previous entry disabled until testing is complete. To roll back, disable
Flux and reverse the entity renames before enabling the previous entry.

Stable Flux values for automations:

| Control | Values |
| --- | --- |
| Preset | `ai`, `powerful`, `night`, `manual`, `natural` |
| Oscillation | `off`, `left`, `right`, `both`, `both_sync`, `both_staggered` |
| Speed | 10% through 100%, in ten physical steps; 0% turns the fan off |

Maintained by **Gabriele Pennacchia**.
