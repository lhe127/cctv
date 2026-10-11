# Township Sentinel — Codex Engineering Instructions

> **Purpose:** This file governs how Codex should design, research, implement, test, and maintain Township Sentinel. It is deliberately **feature-agnostic**. The human owner will specify the feature or change for each task. Do not infer or pre-implement a feature roadmap from this file.

## 1. Mission and operating rules

Township Sentinel is a long-lived, extensible AI/IoT-enabled township operations and safety platform. It may eventually include real-time media, artificial intelligence, connected devices, monitoring, dashboards, integrations, automation, analytics, and other modules. Its exact feature set will be defined incrementally by the owner.

**Non-negotiable objectives:**

1. **Build for maintainability and expansion.** Prefer cohesive modules with stable boundaries over a quick monolithic script.
2. **Reuse before reinventing.** Search the existing codebase and suitable open-source projects/packages before writing a new implementation. Reuse or adapt responsibly when it saves time without undermining quality, licensing, or security.
3. **Implement only the requested scope.** Do not implement speculative features, unnecessary frameworks, unrelated refactors, or an entire roadmap unless explicitly requested.
4. **Encapsulate capabilities behind contracts.** Make functionality accessible through appropriate, documented application interfaces, versioned APIs, or events—without exposing internal implementation details.
5. **Keep components decoupled and replaceable.** External hardware, model frameworks, databases, transports, and vendor-specific SDKs must not leak into business/domain logic.
6. **Prefer virtual-first development.** Functionality must be testable with fixtures, simulations, recorded inputs, and mocks when physical devices are absent. Real devices should be added through adapters later.
7. **Preserve production concerns from day one.** Security, privacy, reliability, observability, and automated tests belong in the design, proportional to the feature's risk.

When the owner gives a task, prioritize their explicit requirements and repository reality over illustrative defaults in this file. Surface any major architectural, licensing, privacy, or safety tradeoff instead of silently violating these rules.

## 2. Required workflow for each new request

### Step 1 — Understand the scope

- Read the owner's current instruction carefully; define expected behavior, inputs, outputs, integration points, and acceptance criteria.
- Inspect the repository, existing architecture, tests, dependencies, conventions, documentation, and previous decisions **before** changing code.
- Identify the smallest meaningful end-to-end change that satisfies the request.
- If a genuinely blocking requirement is unspecified, ask a focused question. Otherwise make and state a reasonable assumption.
- Do **not** add unrelated modules simply because the platform may support them later.

### Step 2 — Research reuse before coding

Search, in this order:

1. Existing first-party project components and utilities.
2. Existing installed dependencies and framework features.
3. Maintained, well-documented open-source libraries and packages.
4. Suitable GitHub projects or reference implementations that can be adapted.
5. A custom implementation, **only** when existing choices are unsuitable or excessive.

For nontrivial functionality, compare the best viable options briefly, including **reuse vs. build**, before committing to one. Prefer established components that solve the problem safely and are straightforward to maintain. Do not rewrite mature functionality merely to claim an original implementation.

**Before adopting GitHub code or model assets, verify:**

- **License:** Is there an explicit license? Does it permit the planned usage, modification, distribution, deployment, and commercialization? An unlicensed public repository is **not** automatically free to reuse.
- **Copyleft obligations:** Assess GPL/AGPL or similar requirements; do not introduce a potentially incompatible dependency or copied code without flagging it and receiving owner approval when needed.
- **AI artifacts:** Independently check code, pretrained model weights, datasets, fonts, images, and sample-media rights. Their licenses may differ.
- **Maintenance:** Recent activity, stable releases, documentation, community support, issue responsiveness, and compatibility with our environment.
- **Security:** Known vulnerabilities, risky install scripts, transitive dependencies, credential handling, and suspicious code. Never blindly execute downloaded scripts.
- **Engineering fit:** API stability, performance, supported operating systems/hardware, testability, integration cost, and risk of vendor lock-in.

**Preferred integration approach:** use an upstream dependency through a narrow adapter. If changes are needed, prefer configuration, composition, extension points, or small upstream-friendly patches over heavily editing vendor code. Fork only for a clear technical reason; record the upstream URL, commit/tag, changes, patch maintenance plan, and license obligations.

**Provenance and attribution:** Preserve required copyright notices, license files, and attribution. Record third-party dependencies and licenses (e.g., in `THIRD_PARTY_NOTICES.md` or an equivalent dependency inventory). Pin or lock dependency versions, use reproducible builds where practical, and track relevant security updates. Never misrepresent upstream code as original work.

If online research is unavailable, explicitly say reuse candidates were not verified; do not invent repositories, URLs, licenses, or security claims. Work from locally available components where possible.

### Step 3 — Plan within the architecture

For a substantial change, prepare a concise plan covering:

- The user-visible behavior and acceptance criteria.
- Modules and contracts affected.
- Reusable components selected, with rationale and license considerations.
- Any new endpoint, event, schema, persistence change, or adapter.
- Testing and rollback/migration implications.

Avoid overdesign. Choose the simplest solution consistent with the platform's boundaries and likely evolution.

### Step 4 — Implement a complete vertical slice

- Implement the requested change end to end, keeping diffs focused.
- Follow the module's public contracts rather than reaching into another module's internals.
- Prefer explicit dependency injection; avoid hidden global service locators and implicit side effects.
- Keep business rules separate from I/O and framework integration.
- Add appropriate error handling, validation, logging, and configuration.
- Do not hardcode secrets, addresses, proprietary file paths, hardware IDs, or environment-specific assumptions.
- Update tests and documentation alongside code.

### Step 5 — Verify and report

- Run the most relevant tests, formatters, linters, type checks, and build checks available in the repository.
- Confirm integration behavior, failure handling, and backward compatibility when relevant.
- Report: what changed, which open-source components were reused (including provenance), any tradeoffs, tests run and their results, configuration needed, and known limitations.
- Never claim a test, license audit, benchmark, hardware check, or deployment succeeded unless it actually did.

## 3. Architectural direction

**Default architecture: a modular monolith for core application logic, with separately runnable workers/processes for resource-intensive or long-running operations.** Evolve toward distributed services only when deployment, scale, fault isolation, or organizational constraints justify them.

Apply Clean/Hexagonal Architecture (Ports and Adapters) pragmatically:

- **Domain:** Core entities, value objects, domain rules, invariants, and domain-level interfaces. No web framework, database client, vendor SDK, transport, or UI dependencies.
- **Application:** Use cases and orchestration; coordinates domain operations via ports. Owns transactions and authorization boundaries where appropriate.
- **Ports / contracts:** Typed interfaces, input/output models, commands, queries, and event definitions. Keep them small and stable.
- **Adapters:** Concrete implementations for databases, media sources, messaging, third-party services, hardware, inference runtimes, and other external systems.
- **Transport / presentation:** Versioned HTTP APIs, WebSockets, graphical interfaces, and command-line entry points; these translate requests into use cases rather than containing business rules.
- **Infrastructure:** Dependency wiring, persistence, deployment, logging, telemetry, secrets, and process configuration.

**Dependency direction:** outer layers depend on inner abstractions, never the reverse. Modules may communicate through deliberately published interfaces or events, not direct imports into another module's internal storage or domain implementation.

Prefer clear interfaces and composition over deep inheritance. Avoid creating an interface for every trivial function; introduce abstractions at genuine variation or integration boundaries.

### Repository organization (illustrative, not a command to scaffold unused folders)

```text
township-sentinel/
├── apps/
│   ├── api/                 # API process / composition root
│   ├── worker/              # Background or compute-heavy workers
│   └── web/                 # User-facing application when requested
├── packages/
│   ├── contracts/           # Shared external contracts/schemas
│   ├── core/                # Minimal cross-cutting primitives
│   └── <domain-module>/
│       ├── domain/
│       ├── application/
│       ├── ports/
│       ├── adapters/
│       └── tests/
├── infrastructure/         # Deploy/run configuration
├── tests/                  # Cross-module integration/contract tests
├── docs/                   # Decisions, architecture, API documentation
└── AGENTS.md
```

Keep a single monorepo initially unless clear requirements favor otherwise. Do not create placeholder folders or boilerplate for unrequested capabilities. Adapt the directory names to the existing repository's conventions.

## 4. API-first and contract-first integration

Expose requested features in a **consistent and easy-to-call interface**, selecting the appropriate boundary:

- **Typed in-process application API** for internal calls.
- **Versioned REST API** (e.g., `/api/v1/...`) for externally called commands and queries.
- **WebSocket / server-sent events** when a client needs live updates.
- **Asynchronous events or commands** when modules should react independently.
- **Specialized media/device protocols** for high-bandwidth or hardware interactions; do not force video frames or continuous telemetry through ordinary REST endpoints unnecessarily.

Rules:

1. Define inputs, outputs, validation, errors, authorization, and contract version before implementation.
2. Keep transport DTOs separate from domain entities and database ORM models.
3. Use descriptive names, consistent pagination/filtering, stable IDs, and explicit timestamps/time zones (UTC in stored events; convert for display).
4. Provide OpenAPI documentation for HTTP endpoints and examples of requests/responses.
5. Maintain backward compatibility when reasonable; otherwise introduce deliberate versioning and migration notes.
6. Do not expose storage internals, implementation class names, raw credentials, or unstable internal metadata as public API fields.
7. Standardize error responses, trace/correlation IDs, and input validation across services.

### Event contract guidance

Prefer a consistent event envelope inspired by CloudEvents where suitable:

```json
{
  "specversion": "1.0",
  "id": "unique-event-id",
  "source": "/components/example",
  "type": "sentinel.example.occurred.v1",
  "time": "2026-10-11T00:00:00Z",
  "datacontenttype": "application/json",
  "data": {
    "resource_id": "resource-123",
    "correlation_id": "request-or-workflow-id"
  }
}
```

- Use explicit event schema versions and consistent naming.
- Include appropriate site/tenant/resource identifiers for authorization and routing, without embedding sensitive payloads unnecessarily.
- Design consumers for duplicate delivery and retry; use idempotency keys, durable publication where needed, and dead-letter/recovery handling when warranted.
- Prefer event metadata and authorized evidence references over large binary payloads.
- A broker is not mandatory initially: an in-process publisher behind a port can later be replaced with a durable broker. Never assume exactly-once delivery.

## 5. Replaceable external dependencies and hardware

**Every external system is an implementation detail behind an adapter.** This includes physical/virtual devices, cloud services, databases, media stacks, inference backends, and messaging systems.

For example, if a requested feature reads external input, define a narrow `Source` interface and provide a simulated or file-backed implementation for tests. A real-device adapter can implement that same contract later. The core use case must not depend on a particular manufacturer's SDK or a fixed connection string.

- Support environment-specific configuration through validated settings and secret management.
- Make resource lifecycle explicit (connect, start, stop, retry, health status, cleanup) where relevant.
- Handle disconnections, bounded queues, cancellation, timeouts, backpressure, and graceful shutdown.
- Distinguish continuous processing from API request handling; never block an API thread with unbounded compute or I/O.
- Make model/runtime selection configurable where technically appropriate (e.g., CPU vs supported accelerators) without contaminating domain rules.
- Use mock/simulated adapters and recorded fixtures to allow feature development without hardware.
- Hardware integration requires compatibility, performance, network, safety, and accuracy validation; an adapter limits rewrites but does not eliminate deployment testing.

## 6. Reusability, performance, and data ownership

- **Single responsibility:** A module owns its data and behavior. Other modules read or act through a public application contract or a well-defined event projection.
- **Shared mechanisms, not tangled business logic:** Share utilities for validation, telemetry, configuration, reusable execution pipelines, etc.; avoid putting unrelated domain concepts into an ever-growing `utils` or `core` package.
- **No duplicated expensive work:** Where multiple requested capabilities need the same computation, reuse an explicitly defined intermediate result or shared service rather than recalculating unnecessarily.
- **Data ownership:** Use repositories or ports, migrations, defined retention rules, and explicit schema ownership. Do not allow modules to write directly to another module's database tables.
- **Scale deliberately:** Measure before optimizing. Profile throughput, memory, latency, queue depth, and resource usage when relevant. Introduce caching, batching, concurrency, or distributed execution only with clear requirements and tests.
- **Multi-site readiness:** Avoid assuming a single township/site. Where relevant, scope resources, permissions, events, and data access by site/tenant identifiers and prevent cross-tenant leakage.

## 7. Secure and responsible engineering

- Implement authentication and authorization at external boundaries; validate object-level access to sensitive resources.
- Default to least privilege, encrypted transport, secure secret handling, and minimal data exposure.
- Do not commit credentials, private recordings, personal data, or proprietary datasets to source control.
- Apply privacy-by-design: collect only necessary information, restrict access, define retention and deletion policies, and audit sensitive operations.
- Treat AI outputs as probabilistic signals rather than unquestionable facts; retain confidence/calibration metadata where useful and provide human review for consequential decisions.
- Do not let a model output alone initiate physically dangerous or irreversible actions without an explicitly designed authorization/safety mechanism.
- Protect integrations from untrusted inputs, dependency supply-chain risks, path traversal, injection, unsafe deserialization, and insecure network exposure.
- Keep security controls relevant to applicable deployment jurisdictions and requirements; flag legal/compliance uncertainty rather than assuming compliance.

## 8. Quality standards and testing strategy

Default expectations, adapted to languages already used in the repository:

- Use clear names, small cohesive units, useful comments, and typed interfaces/type checking.
- Follow existing formatter/linter and coding conventions; set up basic consistent checks if missing and in scope.
- Prefer maintainable dependencies and lockfiles rather than unpinned ad hoc installs.
- Write **unit tests** for domain rules; **integration tests** for adapters, persistence, and APIs; **contract tests** for versioned boundaries; and targeted **end-to-end tests** for user workflows.
- Test errors and edge cases, not just success paths: invalid inputs, timeouts, restarts, loss of connectivity, duplicate events, missing resources, and authorization failures where applicable.
- Use deterministic test data; virtual sources and fixtures must work without physical devices or paid external services when possible.
- Add observability appropriate to the feature: structured logs, contextual IDs, health checks, metrics, and optional distributed tracing. Do not log secrets or sensitive raw media.
- Keep schema migrations reversible or clearly documented. Explain operational changes and any required rollback procedure.
- Use CI to run relevant formatting, linting, type checks, automated tests, dependency/security checks, and builds. Do not invent successful results.

**Suggested defaults, not compulsory choices:** Python/FastAPI for backend APIs, Python for AI/workers, TypeScript/React for web interfaces, PostgreSQL for relational persistence, Docker Compose for local orchestration, and mature open-source adapters/media libraries when needed. Select alternatives based on existing code, actual requirements, licensing, and measured constraints. Do not install a stack merely because it appears here.

## 9. Documentation and architecture decisions

Keep documentation close to the implementation. For material decisions, add a short Architecture Decision Record (ADR) covering context, options, choice, consequences, and potential replacement path. Document:

- The new feature's behavior and configuration.
- Public API/event contracts, including examples and versioning.
- External dependencies, GitHub upstream references, licenses/attribution, and why they were chosen.
- How to run locally with simulated inputs, test, deploy, and troubleshoot.
- Relevant environment variables and operational limitations (without secrets).
- Data schema changes, migration needs, performance assumptions, and security/privacy implications where applicable.

Documentation should describe the implementation that exists; avoid inventing completed modules or pretending placeholder features work.

## 10. Anti-patterns to avoid

- Writing a large `main.py` or one giant service that handles unrelated concerns.
- Starting every capability from scratch without checking existing open-source solutions.
- Blindly copying GitHub repositories, model weights, or snippets without checking license, security, and provenance.
- Editing third-party source throughout our codebase instead of wrapping it behind an adapter.
- Calling another module's private methods or directly accessing its tables.
- Tight coupling between UI, API, business rules, devices, database, and model runtime.
- Overengineering with microservices, Kubernetes, brokers, or complex abstractions before justified.
- Hardcoding camera addresses, credentials, site IDs, absolute local paths, thresholds, or deployment-specific assumptions.
- Duplicated computations that should be shared, or global mutable state shared across unrelated workloads.
- Blocking HTTP endpoints with long-running inference, streaming, or device communication.
- Unversioned API or event changes that silently break clients.
- Swallowing errors, uncontrolled retries, infinite queues, missing shutdown behavior, or unbounded resource use.
- Shipping untested AI claims, treating model confidence as certainty, or automating high-impact decisions without review.
- Adding speculative functionality or scaffolding that the owner has not requested.

## 11. Definition of done

A requested feature or change is done only when, proportionate to its complexity:

- [ ] It fulfills the current explicit request and acceptance criteria, without unrelated scope creep.
- [ ] Existing code and suitable open-source options were examined; chosen reuse is justified and legally/security appropriate.
- [ ] Changes respect module ownership, dependency direction, and replaceable adapters.
- [ ] The capability has a clear internal contract and an external versioned API/event contract **if external access is required**.
- [ ] Configuration and secrets are handled safely; simulation and local testing are possible where appropriate.
- [ ] Automated tests cover meaningful behavior and failure cases; relevant checks actually run, or blockers are disclosed.
- [ ] Security, privacy, reliability, data ownership, and observability considerations have been addressed.
- [ ] Documentation, dependency provenance/attribution, and migration or deployment notes are updated.
- [ ] The final report states what was implemented, what was reused, test results, assumptions, and remaining limitations.

---

### Final instruction to Codex

**Wait for the owner's specific feature request.** Then inspect the repository, look for reusable local/open-source components, plan the smallest maintainable implementation, and deliver it through clean module boundaries and stable contracts. Build a flexible platform **without building unrequested features**. Favor proven, responsibly reused technology over writing everything from zero.
