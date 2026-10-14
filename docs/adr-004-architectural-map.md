# ADR 004: WebGL architectural residential map

## Context

The owner requested a more realistic rendering of the supplied residential plan. The original Canvas 2D polygon renderer could not provide proper occlusion, material lighting, reflections, or shadow maps. The existing layout, directory, and camera API remain suitable for reuse.

## Choice

Use pinned, locally bundled Three.js 0.180.0 with its OrbitControls through the existing async `SentinelResidentialMap.mount(canvas, {root, cameras, onSelect})` boundary. MIT license and hashes are in THIRD_PARTY_NOTICES.md. Preserve the established feature IDs and camera DTOs; there are no backend API or persistence changes.

Separate layout (`map-layout.js`), procedural materials (`map-materials.js`), scene geometry (`map-scene.js`), and renderer/input/lifecycle (`map-renderer.js`). Load the engine only on the map route. Retain the existing stylesheet and inspector. Version the page's scripts/styles to avoid the stale-asset issue observed during development.

Alternatives: further Canvas 2D detail would retain flat lighting and hand-built depth sorting; a custom WebGL engine would duplicate mature renderer and control functionality. Three.js provides these through a maintained dependency without a frontend build system or runtime network requests. Babylon.js would also fit, but adds no required capability over the selected narrow engine integration.

## Consequences

- Real geometry, physical materials, sky reflection environment, shadow maps and accurate mesh picking. Procedural materials and instanced leaf clusters avoid third-party art rights and large asset downloads.
- WebGL 2 is required. Failure is handled by the page's existing error/retry UI with an actionable hardware-acceleration message.
- Pixel ratio and shadow resolution are bounded. Rendering happens on camera, selection, or resize changes. Controls, observers, listeners, GPU geometry, textures and materials are disposed on teardown.
- The result is an architectural approximation, not a photogrammetry reconstruction. No measured elevation/scale is available. Camera marker position and coverage are explicitly illustrative.
- Rollback can restore the previous renderer and HTML script references; no database migration is needed. Future surveyed/GLTF assets can replace scene generation behind the same mounting contract.

## Verification

Real-browser checks cover directory selection and inspector updates, reset, coverage toggle, image changes after zoom and drag-orbit, and a 390px viewport without horizontal overflow. Desktop/detail/mobile screenshots were inspected. JavaScript syntax checks cover all first-party map modules. A local isolated server on port 8765 was used; the user's port 8000 process was not restarted.
