# M3 Polyphonic Audio to MIDI

Status: Tasks 1–10 verified; Task 11 next; not installed.

Source-editable real-time polyphonic audio-to-MIDI for REAPER. The approved
design is linked from the implementation plan. Production code is JSFX/EEL2;
Lua is test orchestration only. The production host path is implemented, but
live-guitar, VSTi-routing, latency, and deadline gates remain unverified; do not
use this build for performance yet.

Task 10 adds double-buffered, generation-checked telemetry; a compact 520x260
performance UI; schema-only project state; 64-sample input-trim smoothing; and
visible overload/fault handling with reachable MIDI cleanup. Cases 10101–10106
passed at 44.1, 48, and 96 kHz in 18 hidden workspace-5 launches. The full
local suite is 45 tests plus a clean source contract. Workspace 1 remained
active and no REAPER process was left running.
