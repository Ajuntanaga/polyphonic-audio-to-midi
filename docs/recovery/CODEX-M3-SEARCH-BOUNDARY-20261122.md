# Project search boundary after the NTFS incident

The 2026-11-21 20:15:25 PST home-directory search was launched by Codex's
`paired_worker_route` helper. It reached the NTFS volume immediately before
the forced restart. Codex owns that mistake. The timing and process ownership
are established; the precise kernel failure mechanism is not.

The user's `DO NOT ENTER` directory, including surrounding spaces or dots,
`Windows.old`, and their contents are forbidden. Do not inspect or resolve
those paths to verify the rule. The checks below used disposable fixtures only.

## Required search route

Parent and project `AGENTS.md` now require every agent and helper to use
`python3 tools/project_search.py` for recursive discovery within the smallest
named project directory. Exact reads of named authorized files remain allowed.
The worker checkout is already known:
`build/recovery/m3-offload-worktree/.github/workflows`. Never search home to
rediscover it. Include the exact roots and this rule in every delegated brief.

The guard:

- Rejects roots outside the project, parent traversal and protected names
  before opening a requested path.
- Opens selected directories without following symlinks, checks device
  identity, and refuses scopes intersecting nested mounts using procfs mount
  metadata. It does not inspect those mounted targets.
- Runs a fixed ripgrep command in a private bubblewrap filesystem, PID and
  network namespace. Only the selected directory, read-only system runtime
  and one installed ripgrep executable are exposed. The host home directory,
  archive mounts and NTFS volume are absent. Temporary storage is private.
- Disables symlink following, config loading and filesystem crossing;
  excludes protected names at every depth, limits depth/file size, uses one
  thread and imposes CPU, memory and elapsed-time limits.
- Stops on isolation failure. There is no unconfined fallback.

This is enforced isolation for searches through the guard, not a machine-wide
restriction on the surrounding Full Access agent or unrelated applications.
Do not bypass it with a direct recursive command. No persistent mount,
permission, service or system configuration was changed.

## Direct verification

`python3 -m unittest tests.test_project_search -v`: **6 passed, 0 skipped**.
The real bubblewrap test found an allowed canary, excluded external symlink
targets and nested protected-name fixtures, and independently verified that
the external fixture path was absent inside the namespace. Other checks cover
lexical rejection before filesystem access, mount metadata, selected-root
symlinks, fixed command arguments and no fallback after isolation failure.

Two setup defects were caught and corrected before reporting success: the
workstation's ripgrep lives in the named user-tool installation rather than
`/usr/bin`, and exclusions needed basename globs to cover nested directories.
Only that executable is bound into the sandbox; its home directory is not.

Actual guarded searches also located `harmonic-source-variation.yml` in the
known worker workflow directory and `render_mixture` in the named source file.
The protected NTFS directory was not accessed during implementation or testing.

The active M3 checkpoint and next paired component/mixture experiment remain
unchanged. This safety fix launched no processing job and changed no installed
tracker or defaults.
