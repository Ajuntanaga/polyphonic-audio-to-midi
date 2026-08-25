# M3 Polyphonic Audio to MIDI — Resume

Updated: 2026-08-25T06:58:45-07:00

## Authoritative state

- Branch: `main`
- Last verified commit: `353080b` (`feat: define fixed memory map and pitch math`)
- Current task: Task 3, input conditioning, levels, and noise floor
- Task 2: committed after both static and real-JSFX verification
- Static result: 5 Python tests pass
- Disposable profile: `build/reaper-test`
- Persistent REAPER profile: untouched

## Current evidence

Run from this repository:

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 tools/validate_source.py .
python3 tools/stage_reaper_test_env.py \
  --reaper /home/ajuntanaga/opt/REAPER/reaper \
  --output build/reaper-test
```

Expected current results: 5 tests pass, `source contract: ok`, and disposable
staging succeeds. The real REAPER JSFX panel passed with 2 assertions and
failed assertion ID 0. Screenshot evidence is retained at
`build/evidence/task-02-core-harness-pass.png` with SHA-256
`ccb7573133e9b054c093e990349d4d7f7518d1c4fa686f7aae182a07b2245c9c`.

## Guarded REAPER boundary

The user approved continued disposable REAPER execution on 2026-08-25. Every
test launch must use only the alternate profile and remain bounded by a transient
user cgroup, CPU affinity, lowered CPU/I/O priority, and a short timeout. The
Task 2 proof used a 512 MiB memory maximum, 64 MiB swap maximum, 50% of one CPU,
32-task maximum, `nice 10`, idle I/O priority, and a 30-second runtime. Observed
REAPER RSS remained about 100 MiB.

Before each launch, stop instead of starting when available memory is below
4 GiB, one-minute load exceeds 12, or a readable thermal zone is at least 90 C.
No audio device is authorized; the disposable instance may report JACK absent.

## Exact resume action

Begin Task 3 with a failing conditioning test in the existing core JSFX harness.
Do not write production conditioning code until the intended RED result is
observed. Keep all REAPER launches under the guarded disposable boundary above.

## Still-gated actions

- dependency download or installation
- persistent REAPER Effects or Scripts installation
- live guitar or audio-interface testing
- live-project modification
- REAPER MCP installation
- native fallback design or implementation
