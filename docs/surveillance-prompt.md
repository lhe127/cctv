# Surveillance prompt

In Settings, click **Use surveillance prompt**, then **Save settings**. Both cameras and algorithm tests use it on their next model call. Existing custom settings are not overwritten automatically.

Copyable criteria (the application supplies the response format):

```text
Inspect the entire scene for visible hazards, including buildings, vehicles, water and people.
Report danger if ANY sampled frame clearly shows a hazard; a later calm frame does not erase it.

Fire: flames on a house, roof, room, vehicle or vegetation, spreading fire, or dense smoke coming from a structure. Fire is danger even when no person is visible.

People: falling or collapsing, lying motionless after a fall, violent punching or kicking, or a visible weapon being used to threaten someone.

Water: a person struggling to stay afloat, repeatedly submerging, or floating motionless; describe possible drowning or distress, not a medical certainty.

Access: climbing over a perimeter wall or fence, forcing a door or window, breaking a lock, or visibly removing property after forced entry. Describe the observed action as possible intrusion or theft; never label a person a thief or infer criminal intent from appearance.

Also flag visible vehicle collisions or a person in an immediate vehicle path.

Ordinary walking, conversation, normal swimming, routine activity, reflections, lights and steam alone are not evidence of danger. Do not infer authorization from appearance. If the action, smoke source or context is unclear, report uncertain.

Describe the specific visible hazard and its location briefly. Do not invent unseen events.
```

## Response handling

The application constrains the generated header to one decision and an `EVIDENCE:` prefix; the model selects the decision and generates the evidence. Its parser also accepts capitalization and spacing differences, and the known missing-D `ANGER:` typo. A response containing both yes and no is **not** automatically converted to danger or safety. It is retried once against the same frames and criteria. A second invalid response is saved as uncertain with an `analysis_warning`, displayed in the camera and algorithm timelines. A valid uncertain response is not retried merely to obtain a positive answer.

This is a broad review prompt, not a validated emergency detector. Small VLMs can miss hazards, hallucinate evidence, or fail the format. Sampled frames can miss brief events. Keep human supervision and independent fire/pool safety measures; do not use this prototype as their replacement. Existing results are not rewritten; rerun a clip after updating the prompt. Uploaded-media alerts remain labeled as recorded media.
