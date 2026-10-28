---
name: mesen2-oos-debugging
description: Debug Oracle of Secrets with an owned Mesen2-OOS socket session. Use for runtime breakpoints, traces, memory, savestate reproduction, crash diagnosis or focused native verification.
---

# Mesen2-OOS debugging

Use the socket client and matching labels to connect observed behavior to source.
Read Oracle's AFS resource rules before native work; keep one owned bounded
headless episode and never target scawful's `oos-rc-play` session.

## Run the focused episode

1. Identify the candidate ROM, symbols, save/fixture, intended behavior and
   existing episode bounds. Acquire ownership under `scratchpad/board_rules.md`.
   A frozen HOLD or failed episode is not permission to retry, extend or relaunch.
2. Use the selected checkout's `Scripts/Mesen2/mesen2_launch_instance.sh` only
   when a new session is needed. Keep current headless/`taskpolicy -b` rules.
   Bind `MESEN2_SOCKET_PATH` to the owned endpoint; verify its ROM identity.
3. Inspect supported client commands with
   `python3 Scripts/Mesen2/mesen2_client.py --help`. Use `health`, `diagnostics`,
   `debug-status` or `capabilities` when that information is needed, rather
   than running a fixed startup suite.
4. Capture one reproduction with the smallest useful breakpoint, trace, memory
   or screenshot evidence. Load labels from this candidate; `labels-sync` is
   vanilla-only. `SYMBOLS_LOAD` accepts `.mlb` or supported JSON; symbol export
   lives at `Scripts/Generate/export_symbols.py`.
5. Run the required changed behavior/control or save/reopen check within the
   accepted bounds. Retain failures and fixture limits. Release only owned
   resources through the current helper after exit/cleanup verification.

Use existing repro/state-library features before writing another driver.
Retry after a changed input, implementation or hypothesis. If native ownership
is blocked, continue source/offline work in scope; wait for its resolver when
nothing useful remains.

## Endpoint and API references

Discovery describes available endpoints; it does not prove ownership. Prefer
an explicit `MESEN2_SOCKET_PATH`. The discovery implementation at
`~/src/hobby/mesen2-oos/socket_discovery.py` can read status-file `socketPath`
values and fallback socket names; names need not contain a PID. Do not select
a live session merely because its status/socket is newest, and do not remove
another owner's socket or lock.

- `~/src/hobby/mesen2-oos/docs/Agent_Integration_Guide.md` — discovery/status.
- `~/src/hobby/mesen2-oos/docs/Socket_API_Reference.md` — actual socket APIs.
- `~/src/hobby/mesen2-oos/tools/oos_client/README.md` — current client location.
- Oracle AFS `scratchpad/operations/oracle.md` — project launch/symbol routes.

Check command details in current client help/source before using a historical
skill-local cheatsheet. Runtime writes, controller input and fixture injection
must remain within the accepted episode; source/build evidence and sampled
telemetry retain their actual scope.
