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

If it does, **requirements-impact-refiner is required** before planning or implementation. Invoke it automatically; do not wait for the user to name it. Respect its selected workflow adapter: with Superpowers, run it after approved brainstorming and before `writing-plans`; otherwise run it before the user's planning method.

The core skill defaults to one Fast Scan, returns its display text, asks whether to refine, and stops. Do not substitute manual searches or graph JSON. Only an explicit yes enters detailed report lineage; never infer a missing predecessor.

Skip it for pure ideation, explanation, debugging, code review, status checks, and execution of an already impact-refined requirement or plan.

In plugin-capable clients, the plugin's enabled/disabled control is the on/off switch for this automatic check.
