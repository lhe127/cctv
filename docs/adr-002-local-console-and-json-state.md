# ADR 002: Routed local console and JSON state adapter

- **Status:** Accepted
- **Date:** 2026-10-12

## Context

The prototype had one embedded dashboard at `/`, in-memory alerts, and camera configuration loaded from JSON. The requested management experience needs distinct page routes, API-key sign-in, camera CRUD, semantic polygon drawing, a map, persistent alert history, and image/video algorithm tests. The project remains a single-process local prototype and should not gain a separate frontend toolchain or database before either is justified.

## Options considered

1. Add React and a relational database now. This offers a broad ecosystem, but adds a build pipeline, migrations, and deployment surface beyond the current need.
2. Keep one in-page view switcher and in-memory state. This is smallest, but does not satisfy distinct URLs or restart-safe alert history.
3. Reuse FastAPI with a buildless shared console shell, real server routes, atomic JSON adapters, and a bounded background inference runner.

## Decision

Use option 3.

- FastAPI serves `/login`, `/dashboard`, `/cameras`, `/robots`, `/map`, `/alerts`, and `/algorithm-test`. The authenticated console uses a shared HTML/CSS/JavaScript shell, while browser navigation retains real URLs.
- The API key is validated through `/api/v1/session` and retained only in `sessionStorage`. This is a local shared-secret mechanism, not full identity management.
- `JsonCameraRepository` owns camera configuration and `JsonStateStore` owns bounded alert and algorithm-test history. Both use temporary-file replacement for atomic writes.
- `MonitorService` depends on an event-store protocol rather than JSON details.
- `AlgorithmTestRunner` uses the existing detector contract on a single background executor. It bounds uploads to 100 MB and video processing to 60 seconds.
- Camera source values remain write-only at the API boundary; clients receive sanitized source labels so RTSP credentials are not exposed.
- Google Maps is an explicit temporary external embed. No location data is persisted by the application yet.

## Consequences

The implementation stays dependency-light, runs without a frontend build, and remains virtual-first. Routes can later be replaced by a richer frontend without changing versioned APIs. JSON persistence is easy to inspect and back up, but only supports a single application process and has no transactional querying, multi-tenant isolation, or fine-grained retention. A database adapter should replace it before multi-process or production deployment. Background algorithm tests are serialized and restart-interrupted jobs are marked failed; a durable work queue can replace the runner when scale or fault recovery requires it.

No new package or copied-source license obligation is introduced. The existing FastAPI, OpenCV, NumPy, and model provenance applies; the Google Maps service considerations are recorded in `THIRD_PARTY_NOTICES.md`.
