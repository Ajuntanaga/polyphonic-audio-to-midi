# M3 workspace rules

Read the top of `RESUME.md` for the active checkpoint before continuing work.
Preserve unrelated working-tree changes and the installed plugin.

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
