# V4 Task 0B4c — Controlled Non-REAPER Fixture Definition

**Status:** draft, source-free design only. The user has authorized the project
roadmap, so this record may define the fixture while the immediately preceding
bootstrap-transport and mock-only state checkpoints remain pending independent
review. It does not satisfy their review requirement, create a manifest, or
authorize any process, namespace, mount, Bubblewrap/systemd command, REAPER,
audio, X11, network, or host action.

## Purpose and boundary

The one bounded fixture will eventually test the session-control path, not
REAPER compatibility or live MIDI. It will prove only that one reviewed session
root either emits the valid `PRE -> ACK+EOF -> POST` exchange around one
non-REAPER direct child, or fails closed without a terminal receipt. It will
never scan a plug-in, open an audio device, connect to an X server, or load a
REAPER binary.

This design is explicitly not executable today:

1. `tools/reaper_v4_session.py` still has fail-closed runtime evidence and
   payload-assembly stubs.
2. The bootstrap-transport and state source checkpoints have local 46-check
   evidence at SHA-256
   `5aaeef6dcf84ac988fa537e63cf7016fde03c46fcbc755d71886133186687e38`, but
   remain pending their independent review.
3. Task 0B5 has not constructed a complete runtime graph, and no reviewed
   `fixture-runtime-manifest` exists.

Those conditions are intentional hard stops for fixture execution. Drafting the
fixture definition now reduces ambiguity without bypassing any of them.

## Single fixture topology

The future outer harness owns every capability outside the one session process:

```text
retained parent/harness
  owns config + digest sources, manifest identities, fixture tree, stdout/stderr drains,
  ACK writer, timeout/teardown accounting, and the direct-child census
       |
       | fd 0: exactly b"\x06", then EOF
       | fd 1: at most PRE and POST frames, each <= 2,064 bytes
       | fd 2: at most one <= 1,024-byte diagnostic
       v
one same-namespace session root
  fixed config paths only; no inherited control/root descriptor; own evidence FDs
       |
       v
one direct non-REAPER child: /usr/bin/true
```

The future scope mechanism is the already-designed Bubblewrap-based
non-REAPER fixture mechanism. An execution authority must name and review its
exact version and argv policy; it may not replace it with an `unshare`, shell,
or ad-hoc launcher. This document does not form that command.

The parent begins bounded, concurrent drains of fd 1 and fd 2 before the scope
starts. It accepts a complete result only if it decodes exactly one PRE, sends
the exact ACK and closes its writer, decodes exactly one terminal POST, observes
both output EOFs, obtains clean scope/child accounting, and verifies its
retained baselines. A partial frame, non-EOF stream, diagnostic overflow,
timeout, child uncertainty, or cleanup/census uncertainty is nonterminal and
is recorded as fixture failure without retry.

## Fixed fixture data

The fixture data plane contains no executable plug-in, REAPER artifact, audio
endpoint, or host home tree.

| In-namespace role | Required shape | Bound |
| --- | --- | --- |
| `/run/m3-v4/session-config.json` | canonical JSON SessionConfig | <= 8,192 bytes |
| `/run/m3-v4/session-config.sha256` | exactly 64 lower-case hex bytes, no newline | 64 bytes |
| measurement root | one regular `display` resource | mode 0444, size 0 |
| private scan root | exactly `a/plugin.vst3 = b"A"` and `b/plugin.vst3 = b"BC"` | mode 0444, sizes 1 and 2 |
| private home | mode 0700, exact empty `.vst` and `.vst3` directories | no extra entry |
| private Xauthority | one regular mode-0600 fixture file | <= 65,536 bytes |
| private X socket | one Unix-domain socket used only for identity checks | no client or X protocol traffic |
| direct child | `/usr/bin/true` with the admitted six-key environment | one launch, exit 0 |

The configuration and fixture-data inputs are separate from the future Python
runtime closure. Task 0B5 must enumerate the executable session root, Task 0A,
and Task 0B1 runtime Python/extension/ELF edges before a fixture manifest can
name their individual regular files. No broad `/usr`, `/lib`, repository, home,
or runtime-directory bind is allowed.

## Concrete resource policy for the fixture data plane

The fixed per-run limits are:

- one session process and one direct child only;
- `pre_deadline_ms = ack_deadline_ms = post_deadline_ms = 5000` and
  `child_timeout_ms = 30000`, so the harness imposes a 45-second total
  control-path deadline before teardown accounting;
- fd 0 carries exactly one byte, fd 1 carries at most two 2,064-byte frames,
  and fd 2 carries at most one 1,024-byte diagnostic;
- the session inherits exactly fd 0, fd 1, and fd 2; after closing its two
  bootstrap readers it may retain only the five named evidence descriptors;
- the fixture-data table has at most seven regular inputs (config, digest,
  measurement resource, two scan files, authority, and direct child), at most
  16 KiB total excluding the eventual runtime closure, and no individual
  fixture-data file larger than the applicable session limit.

Task 0B5's sealed resource policy must add the exact runtime-closure regular
entry count, copied bytes, largest entry, data-FD count, directory/stdio/temp
FD equation, soft-`RLIMIT_NOFILE` headroom, private-tmpfs size, and memory
ceilings. The outer harness observes those actual limits before execution and
refuses when they are smaller than the sealed requirement.

## Required fixture cases

The later fixture harness must run each row once, with no retry or fallback:

| Case | Parent action | Required result |
| --- | --- | --- |
| positive control path | decode PRE, send ACK then EOF | one direct `/usr/bin/true`, one POST, clean EOF and teardown |
| malformed ACK | write any byte other than `0x06` or leave a trailing byte | PRE-only; no child and no POST |
| missing ACK EOF | write `0x06` but keep the writer open | PRE-only; no child and no POST |
| pre-evidence refusal | alter a declared fixture fact before PRE | no child and no POST |
| post-baseline drift | mutate the private scan tree after PRE | no terminal POST |
| child uncertainty | make the one child time out, signal, or return negative | PRE-only and outer teardown/census |
| output uncertainty | force short/error PRE or POST write, output-drain error, or deadline expiry | no accepted terminal result |

The test matrix does not claim the synthetic data has REAPER semantics. It
exists solely to exercise the exactly-one-root and bounded-control invariants.

## Entry conditions for execution

All of the following must be true before any `Task 0B4c-execution` command is
formed or run:

1. Bootstrap-transport and state source checkpoints are independently reviewed
   and sealed, including the current nonblocking-pipe and one-shot-release
   regressions.
2. A reviewed source gate replaces the current fail-closed runtime
   evidence/payload stubs with named, bounded implementations and negative
   tests. It must not add a second coordinator or an alternate control channel.
3. Task 0B5 produces `COMPLETE_FIXTURE_CANDIDATE` from the exact session root;
   any unresolved graph edge stays blocked.
4. A fixture-runtime manifest individually pins every runtime and fixture input
   and independently passes closure and resource-policy review.
5. A separate execution authority names the reviewed outer mechanism, exact
   fixture policy, drains, teardown, and census checks.

No state described above authorizes a REAPER host row. A later host-runtime
manifest and a separate host request remain required for that goal.
