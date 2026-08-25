Fast impact scan needs more input. Candidate boundaries: no repository-backed candidate. Coverage: needs_input; 3221 ms; cache bypassed.

The requirements-impact-refiner Fast Scan ran against /Users/p042890/workspace/polaris and returned `needs_input` (display text above, verbatim): it found no trustworthy repository-backed seed for this change and produced zero candidate boundaries.

I independently verified why: none of the supplied evidence exists in this repository. Searches across the whole repo (excluding node_modules/.git) found no occurrence of `authorizeProjectEdit`, no workspace-member or invitation code, and no actor-role audit event — not even the word "role" in the backend or contracts/ directories. The "repository evidence" in the request does not correspond to the polaris codebase, so the scan cannot anchor an impact analysis.

To proceed, one concrete repository-backed boundary is needed — an actual file path, module, or symbol in this repo where project-edit authorization (or its equivalent) lives, or confirmation of which repository the evidence refers to. Please ask the user for that boundary (or the correct repo) before any refinement or implementation is attempted; no code changes were made.
