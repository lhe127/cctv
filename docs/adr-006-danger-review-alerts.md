# ADR 006: Explicit model danger results and review alerts

## Context

The owner requested automatic danger logging, pending/resolved states, and pending alerts on the residential map. Existing model output was prose, with reusable inference, JSON storage, camera coordinates, and a Three.js renderer already available.

## Decision

Append an explicit three-state output contract to the configurable prompt. The adapter parses an exact first-line decision and evidence into the model-independent `VisualFinding.danger_status`. Prose keyword matching was rejected because negations and uncertainty easily produce misleading alarms. A second model invocation or new model dependency would add cost without validated accuracy benefits; the existing model remains the only inference adapter.

The configured prompt, shared by cameras and algorithm tests, owns the danger criteria and exclusions. Appended instructions specify the decision format and evidence requirement, not an additional danger taxonomy that could override the owner's prompt. The editable default supplies example criteria; existing saved prompts are never overwritten during upgrade.

`AlertService.record_finding` is the application function called by live findings and recorded-media windows. It creates a review-required pending alert only for `yes`, behind an `AlertStore` port. The existing JSON adapter provides atomic creation and status updates with finding-ID idempotency. No generated code or arbitrary model function call is executed. Physical actions remain out of scope.

Authenticated versioned list/update APIs drive the alert page and five-second map refresh. Camera identity and coordinates are snapshots, not invented locations; colocated pending alerts share a counted pin and remain individually listed. Unplaced alerts remain visible in the map sidebar. Resolved alerts remain in history and can be reopened.

## Consequences and replacement path

Old findings without classification stay uncertain; old state files need no destructive migration. Model format compliance and danger accuracy are not guaranteed. Missing/malformed decisions never silently become positive or safe classifications. The UI marks these outputs as requiring review. Fixture tests validate orchestration and parsing, not model accuracy.

One alert is created per flagged window, not per deduplicated real-world incident. History is retained without truncating pending alerts, so JSON size must be monitored. This single-process local prototype has shared-key operator access and last-write-wins status changes, not per-person audit trails. A transactional database and pagination can replace `AlertStore` without changing inference or the application service. No new libraries, copied third-party code, or model assets were adopted.
