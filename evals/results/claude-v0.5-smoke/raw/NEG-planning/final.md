The plan is complete and self-reviewed. Final report:

## Summary

I used the **superpowers:writing-plans** skill (requirements-impact-refiner correctly excluded — the impact report is already approved) and turned the approved specification into coding tasks.

**Spec identified:** `/Users/p042890/workspace/polaris/submission/1_기획서/01_MVP_개발범위.md` — v2, explicitly marked approved ("출발지·목적지 이원 패키지 모델을 Must로 승인"), covering Must items M-01 through M-08, grounded against `contracts/openapi.yaml` v0.4.0, the ERD (09), and the IA (08).

**Scope check outcome:** The spec spans multiple independent subsystems, so it was decomposed into a 7-plan sequence (documented in the plan header): package domain → bindings/finalize + M-07 asymmetric control → rule engine + review/approval → mock provisioning → AI recommendation + LLM safe mode → session auth/dashboard → frontend wiring + deploy.

**Deliverable:** `/Users/p042890/workspace/polaris/docs/superpowers/plans/2026-08-25-package-domain-backend.md` — Plan 1 (M-01 package domain backend, the foundation every other Must item consumes), written in full bite-sized TDD detail:

- 9 tasks, each with failing-test → run → implement → run → commit steps and complete Java code (no placeholders): version state machine per IA 4.9.2, `SourcePackage` and `DestinationPackage` aggregates, synthetic `ProjectMember` read model + seeds, persistence adapters mirroring the existing hexagonal `request` domain, `PackageService` with list filters/paging, and `PackageController` implementing the contract's `/api/v1/packages` operations with error-code mappings.
- Explicit seams for later plans (a zero-count link-stub adapter Plan 2 replaces; `DEMO_PROJECT_ID` Plan 6 replaces).
- Two documented spec conflicts resolved contract-first: ERD's `DEV/TEST/PROD` vs contract's `DEV/STAGE/PROD` (contract wins, erratum flagged), and a 409 on draft-edit the contract omits.

**Next decision needed from the user (execution handoff):** run Plan 1 via **subagent-driven development** (fresh subagent per task, recommended) or **inline execution** (executing-plans, batched with checkpoints) — in an isolated worktree/branch such as `feature/backend-package-domain`, not on `main`.
