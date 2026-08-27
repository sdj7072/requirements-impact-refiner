---
name: using-requirements-impact-refiner
description: Use when starting any software-development conversation - determines whether a concrete proposed behavior change needs requirements impact refinement before planning, implementation, or ANY repository modification; a direct imperative you could execute immediately (delete X, rename Y, let members do Z) is still a behavior change and fires this check first
license: MIT
compatibility: Works with Agent Skills clients that support automatic skill discovery.
metadata:
  version: "0.6.0"
---

# Using Requirements Impact Refiner

Before any response or action, check whether the current request proposes adding, changing, renaming, migrating, or removing software behavior.

An imperative you could execute immediately is still a behavior change — being able to act is not permission to skip refinement. Do not modify the repository before the impact report exists; if you notice you have already started acting, stop and refine first. The report is the deliverable that earns the change.

If it does, **requirements-impact-refiner is required** before planning or implementation. Invoke it automatically; do not wait for the user to name it. Respect its selected workflow adapter: with Superpowers, run it after approved brainstorming and before `writing-plans`; otherwise run it before the user's planning method.

For a selected change, read [Previous-report bootstrap](../requirements-impact-refiner/references/previous-report.md), call `rir_previous` before any `rir_scan`, and follow its route. Forward stale identity only as the exact delta hint set the tool returned. Return renderer text; never substitute searches, graph JSON, or an invented report. Report flow enters detailed refinement immediately after a non-`needs_input` scan; ask flow enters it only after a later explicit yes to that scan's refinement question. Original request wording is not ask-flow confirmation.

The default report flow returns a fresh previous report directly or uses a stale/none scan to seed immediate detailed refinement. The opt-in ask flow returns the scan summary and waits for a later explicit yes. `needs_input` and `ambiguous` always stop for user input.

For pure ideation, explanation, debugging, code review, status checks, and execution of an already impact-refined requirement or plan, call neither `rir_previous` nor `rir_scan`.

In plugin-capable clients, the plugin's enabled/disabled control is the on/off switch for this automatic check.
