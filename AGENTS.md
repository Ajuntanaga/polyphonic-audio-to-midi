# M3 workspace rules

Read the top of `RESUME.md` for the active checkpoint before continuing work.
Preserve unrelated working-tree changes and the installed plugin.

## Codex and Claude are peers

The user explicitly authorized both collaborators to advance this project.
Either may design, implement, analyze, commit, push, collect artifacts and
dispatch jobs within the existing user-authorized scope. Neither needs the
other's approval, and neither is restricted to proposing work for the other.
The standing CPU-job authorization applies to both; it does not appoint an
exclusive execution or integration owner.

- Record the intended files/workstream and check the current checkpoint before
  editing shared code or dispatching, to avoid conflicting writes or duplicate
  jobs. Ownership is temporary coordination, not authority over the other peer.
- Each peer may carry its own work through implementation, verification and
  publication. A message or acknowledgement from the other is not a gate.
- Do not mark the other peer paused unless that peer or the user explicitly
  says so. A watcher expiring or a missing reply is not a pause instruction.
- User resource, filesystem, installed-output and scientific constraints apply
  equally. Keep the existing GitHub route for recorded-input processing.
- Current coordination: `docs/recovery/CODEX-M3-PEER-COLLABORATION-20261122.md`.
  Its correction supersedes older Codex-exclusive or "Claude paused" statements.

## Filesystem boundary — applies to every agent and helper

The user has forbidden access to `Windows.old` and its containing
`DO NOT ENTER` directory (including spelling with surrounding spaces or a dot).
A helper's unbounded home-directory `find` reached the NTFS volume immediately
before the 2026-11-21 forced restart. Do not repeat that discovery pattern.

- Never recursively search `/`, `/home`, the user's home, an archive root,
  a mounted-volume root, or a parent of this checkout. Never inspect, stat,
  resolve, read, hash or use the protected directory or its contents.
- Use `python3 tools/project_search.py` for recursive filename and content
  searches. Give the smallest known project directory, never a guessed parent.
  It runs ripgrep in an isolated, read-only filesystem view; failure is final
  for that attempt. Do not fall back to an unconfined search.
- Do not replace this guard with `find`, `os.walk`, `Path.rglob`, `glob("**")`,
  `du` recursion, or ripgrep's symlink-follow option. An empty result is not
  permission to widen the search outside the project.
- Exact reads of already named, authorized files are allowed. System runtime
  files, `/proc` metadata and the configured memory index may be read by exact
  path; this does not authorize discovering files under their parent trees.
- Every delegated task must state the exact allowed roots and this boundary.
  The lead is responsible for helpers' searches. Do not delegate home or
  volume discovery.
- Source root: this checkout. Worker checkout: the already known
  `build/recovery/m3-offload-worktree`. Its workflow directory is
  `build/recovery/m3-offload-worktree/.github/workflows`.
  If a recorded path is absent, report that; do not search home for another copy.

Examples from this checkout:

```sh
python3 tools/project_search.py files tools --glob '*harmonic*'
python3 tools/project_search.py text tools 'render_mixture' --glob '*.py'
python3 tools/project_search.py files build/recovery/m3-offload-worktree/.github/workflows
```

The guard confines searches launched through it. The surrounding Codex session
still has Full Access; these rules do not claim a machine-wide access ban.
Audio, model inference, native builds and corpus execution stay on GitHub
Actions under the current checkpoint. Never launch duplicate processing.
