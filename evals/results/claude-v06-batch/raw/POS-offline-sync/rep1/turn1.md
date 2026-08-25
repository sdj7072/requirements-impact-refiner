Done. The repository contained only three constant stubs, so the deliverable is a new sync module built around the constraints those stubs document.

**What was implemented**

`/private/tmp/claude-501/-Users-p042890-workspace-polaris/074a0f85-287f-4435-929b-4948eb69c993/scratchpad/batch-v06/POS-offline-sync/rep1/client/sync.py` — `OfflineSync.on_reconnect()` drains the `offline.edits` queue and replays it against the server. Each piece of repository evidence maps to a design decision:

1. **`updated_at` stamped on every record** (`models/record.py`) → conflicts are resolved last-write-wins: a queued edit is dropped if the server copy's `updated_at` is newer, applied otherwise.
2. **24-hour tombstone retention** (`server/tombstones.py`) → two behaviors: (a) an edit older than a live tombstone is dropped (the delete wins), while an edit newer than the tombstone recreates the record; (b) if the client was offline longer than `TOMBSTONE_HOURS`, deletions during the gap may have aged out and are undetectable, so the sync still replays edits but forces a **full snapshot resync** of the local store instead of trusting incremental state.
3. **Queue preserves local creation order only** (`client/queue.py`) → replay walks the queue in that order (so later local edits to the same record supersede earlier ones), but never uses queue position to order against server writes — the `updated_at` stamp settles every server conflict.

The module imports its constants from the three existing files (`STREAM_LINK`, `STAMPED`, `TOMBSTONE_HOURS`) rather than redefining them, and takes `Server`/`EditQueue` protocols so transports are injectable.

**Verification**

`/private/tmp/.../rep1/tests/test_sync.py` — 8 tests covering newer-edit-wins, stale-edit-dropped, tombstone-beats-edit, edit-beats-tombstone (recreate), local-order replay, >24h-offline full resync (purges a ghost record the server deleted after tombstone expiry), within-window incremental, and delete-edit application. All 8 pass (run with a plain-Python runner since pytest isn't installed on this machine; the tests use only bare asserts so pytest will also run them as-is).