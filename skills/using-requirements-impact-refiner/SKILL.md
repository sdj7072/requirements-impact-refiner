---
name: using-requirements-impact-refiner
description: Use when starting any software-development conversation - determines whether a concrete proposed behavior change needs requirements impact refinement before planning or implementation
license: MIT
compatibility: Works with Agent Skills clients that support automatic skill discovery.
metadata:
  version: "0.5.0"
---

# Using Requirements Impact Refiner

Before any response or action, check whether the current request proposes adding, changing, renaming, migrating, or removing software behavior.

If it does, require **requirements-impact-refiner** before planning or implementation. With Superpowers, run it after approved brainstorming and before `writing-plans`; other adapter boundaries stay unchanged.

For a selected change, read [Previous-report bootstrap](../requirements-impact-refiner/references/previous-report.md), call `rir_previous` before any `rir_scan`, and follow its route. Return renderer text; never substitute searches, graph JSON, or an invented report. Only a later explicit yes to a non-`needs_input` scan's refinement question enters detailed refinement; original request wording is not confirmation.

For pure ideation, explanation, debugging, code review, status checks, and execution of an already impact-refined requirement or plan, call neither `rir_previous` nor `rir_scan`.

In plugin-capable clients, the plugin's enabled/disabled control is the on/off switch for this automatic check.
