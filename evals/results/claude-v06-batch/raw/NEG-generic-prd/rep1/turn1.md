PRD complete and published.

**Artifact:** https://claude.ai/code/artifact/235739f6-e138-4804-b710-e4f3ff277ed0 (POLARIS PRD, v1.0, Korean — matching the repo's documentation language)

**Product identified from the repo:** POLARIS is an enterprise access-policy lifecycle platform (hackathon finals MVP). It replaces per-policy firewall/server/DB access requests with a dual-package model — a per-member "인력·출발지 패키지" (source: infra environments LOCAL/MYDEK/DEVDI/OTHER with hosts and IP/CIDR endpoints) linked to versioned "목적지 패키지" (destination: server/DB/site resources per role/duty) — flowing through AI recommendation → rule-engine + AI security review → customer approval → automatic mock provisioning → verification → automatic revocation.

**PRD contents (14 sections):**
1. Problem definition (30-min manual requests, missed/excess permissions, stale access, provisioning drift)
2. Goals with quantitative targets (≤5 min bulk request, ≥90% defect detection, ≥9/10 demo repeatability) and MVP done criteria
3. Four login roles (PROJECT_PRACTITIONER, SECURITY_REVIEWER, CUSTOMER_MANAGER, SYSTEM_ADMIN) plus non-login project members
4. Domain model incl. Desired vs Effective state
5. Functional requirements M-01–M-08 traced to F-* IDs, plus Should/Could table
6. AI requirements (AI-02/03/04 Must, AI-01 undecided), non-AI deterministic boundaries, LLM safe-mode
7. Demo user flows SC-00–SC-06
8. State models (request and package-version transitions, DRAFT→…→REVOKED)
9. NFRs (security, reproducibility, UX principles from DESIGN.md)
10. Explicit out-of-scope (intentional tailoring)
11. Tech overview (Next.js / Spring Boot / Supabase JDBC / single LLM orchestrator, contract v0.4.0)
12. Milestones and pre-agreed scope-reduction dates (8/26–9/2 code freeze)
13. Risks + open issues (RLS decision pending; AI-01 priority decision)
14. Traceability matrix (M-* ↔ SC-* ↔ F-*)

The centerpiece is **M-07 asymmetric control** — removed policies auto-revoke without approval; added policies require PL confirmation, security review, and customer approval — flagged as the non-negotiable differentiator per the scope doc.

**Sources:** `/Users/p042890/workspace/polaris/submission/1_기획서/01_MVP_개발범위.md` (v3), `02_사용자_데모_시나리오.md`, `03_제약사항_및_가정.md`, `04_기능목록_AI_식별.md`, `DESIGN.md`, `README.md`. The PRD notes that on conflict the repo originals remain authoritative (01=M-*, 02=SC-*, 04=F-*/AI-*). Design honors the repo's own POLARIS design system (midnight-navy dark-first with starlight accent, Geist/Geist Mono + Noto Sans KR), with a derived light theme.

[collection note: the run completed in the prior session; its transcript file was pruned on restart, so this file preserves the final report as delivered in the completion notification rather than a transcript re-extraction.]
