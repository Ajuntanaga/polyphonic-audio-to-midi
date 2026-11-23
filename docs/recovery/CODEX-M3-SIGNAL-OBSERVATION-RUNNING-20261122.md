# Signal observation diagnostic running

Run **45106622018** in `Ajuntanaga/m3-offload`, workflow
`signal-observation-stages.yml`; source `7a5dc0519b7d8429290dd7cd9cba9ac1ad1720e7`,
worker `818b51ef13623087034e87a719eec49e30ee7632`. One dispatch.
The pinned inputs and 25 runner contracts pass; native build is running.
Source checks are portable **45106553048** and CI **45106553050**.

This is the fixed three-case/four-control observation in
`CODEX-M3-SIGNAL-OBSERVATION-PLAN-20261122.md`. No policy or optimization is
being screened. The snapshot hashes must retain identity and allocations/frees
must be zero. The compiler switch is OFF in production.

Collect `m3-signal-observation-report-45106622018-1` once into
`build/github-results/signal-observation-stages-45106622018`; keep
`m3-signal-observation-evidence-45106622018-1` remote. All three rejected
optimization screens remain closed.

Claude: the attack-zone finding is recorded in the plan; no duplicate count or
replay is needed. It leaves acoustic re-pluck preservation open. This CPU
observation is independent of your tracking work.
