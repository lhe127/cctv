# ADR 001: Webcam behavior review signals

## Context

A01–A06 use the existing OpenCV capture and YOLOX detection pipeline. A07 (wall climbing) and A08 (door tampering) require temporal behavior evidence and scene geometry. No labeled clips from the intended wall or door view are available in the repository. The sample zones are illustrative.

## Options considered

Public footage was checked as a fallback. [OTW](https://github.com/stresearch/otw) is CC BY 4.0 and labels ordinary door opening and closing, but not forced entry; its published archive is 48 GB. The [MEVA paper](https://arxiv.org/abs/2012.00914) reports CC BY 4.0 footage with facility-door actions, but its listed classes do not include wall climbing or door tampering. [SPHAR](https://github.com/AlexanderMelde/SPHAR-Dataset) requires checking each underlying video's separate license. None supplies a suitable, small, licensed, labeled positive/negative set for both target behaviors, so no third-party footage was copied or used to claim accuracy.

- Reuse the installed OpenCV capture, detection, and frame-processing stack, with configurable zone rules. This has no new model or package dependency, but produces review cues rather than action classification.
- Add [OpenCV Zoo's pose estimator](https://github.com/opencv/opencv_zoo/tree/main/models/pose_estimation_mediapipe). Its directory declares Apache 2.0 for files and weights, but keypoints alone do not establish climbing or forced entry. It adds another model and inference pass.
- Add [MMAction2](https://github.com/open-mmlab/mmaction2), an Apache 2.0 action-recognition framework. It requires PyTorch and related OpenMMLab packages; an off-the-shelf action model still needs suitable classes and validation on the target scene.
- Add Ultralytics pose or action assets. The [published license options](https://github.com/ultralytics/assets/blob/main/README.md) include AGPL-3.0 and a commercial license, so this is deferred pending an explicit licensing decision.

## Decision

Keep the existing OpenCV and YOLOX adapters. Require sustained upward travel for A07 and consecutive local motion observations for A08. Suppress broad frame changes that likely indicate lighting or camera movement. Expose thresholds through zone configuration and provide an authenticated zone editor. Label both outputs as **suspected** and require human review.

## Consequences and replacement path

The rules are runnable from a webcam and remain independent of the capture source, so RTSP CCTV can use the same contracts. They cannot establish intent, climbing, forced entry, or damage. Before deployment, collect consented scene-specific positive and negative clips, annotate event times, measure false alerts and missed events, and tune or replace the behavior adapter. A future licensed, validated model can enrich observations without changing the camera API or zone/event contracts. The OpenCV Zoo and MMAction2 candidates were researched but not installed or copied.

2026-10-12 update: Local test files are now paced by their recorded FPS and stop at EOF. A07 can require an optional horizontal fence-top crossing line. A08 video processing uses a small handle-zone polygon and surrounding-motion suppression, with no person detection required; its events have null track and kind fields. These are still heuristic review signals. The supplied normal door-opening clip serves as a negative check. No new dependency or model was introduced.

Later 2026-10-12 update: A staged lock-tool clip was added as a limited positive check. Flashlight and hand movement made the absolute surrounding-motion threshold miss this clip; A08 now requires motion concentrated in the lock zone relative to its surroundings. The capture worker samples A08 motion independently of YOLOX so short interactions are not lost to inference timing. A demonstration config uses more sensitive thresholds than the webcam example. This is a clip regression result, not measured field accuracy.
