---
name: using-requirements-impact-refiner
description: Use when starting any software-development conversation - determines whether a concrete proposed behavior change needs requirements impact refinement before planning, implementation, or ANY repository modification; a direct imperative you could execute immediately (delete X, rename Y, let members do Z) is still a behavior change and fires this check first
license: MIT
compatibility: Works with Agent Skills clients that support automatic skill discovery.
metadata:
  version: "0.6.2-dev"
---

# Using Requirements Impact Refiner

Before any response or action, check whether the current request proposes adding, changing, renaming, migrating, or removing software behavior.

An imperative you could execute immediately is still a behavior change — being able to act is not permission to skip refinement. Do not modify the repository before the impact report exists; if you notice you have already started acting, stop and refine first. The report is the deliverable that earns the change.

If it does, **requirements-impact-refiner is required** before planning or implementation. Invoke it automatically; do not wait for the user to name it. Respect its selected workflow adapter: with Superpowers, run it after approved brainstorming and before `writing-plans`; otherwise run it before the user's planning method.

Before any RIR tool, require both substantive product behavior and an inspectable repository scope or evidence target. A generic PRD request missing either input is ideation: ask only for the missing behavior and scope, and call neither `rir_previous` nor `rir_scan`.

For a selected change, invoke `requirements-impact-refiner` and follow it. The invoked skill owns previous lookup, scan, confirmation, detailed refinement, renderer output, and the terminal stop.

After successful finalize, Return `display_text` verbatim and end the current turn.

For pure ideation, a generic PRD, explanation, debugging, code review, status checks, and execution of an already impact-refined requirement or plan, call neither `rir_previous` nor `rir_scan`.

In plugin-capable clients, the plugin's enabled/disabled control is the on/off switch for this automatic check.
