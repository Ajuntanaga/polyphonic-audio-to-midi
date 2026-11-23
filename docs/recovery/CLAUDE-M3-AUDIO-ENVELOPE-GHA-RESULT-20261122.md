# Audio envelope at all seven suppressed NoteOns, on GitHub Actions (POST HOC)

No local download, per the user: worker workflow `audio-envelope-check.yml` (worker commit `485d77f`), one dispatch, run
**45152438887** (success), reading the pinned input release `corpus-20261108` (sha256 `adf6e36f…4254`, checked on the runner).
Samples are Codex's removed NoteOns (`CODEX-M3-STABLE-NOTE-ATTACK-TIMING-20261122.json`). Same method as the local
constructed check (nominal-pitch band, ±4% here instead of ±3%; 5 ms Hilbert envelope). Output read from the run log; the
14-day report artifact (`audio-envelope-45152438887`) was not downloaded. Not pre-registered.

Pipeline check: the four constructed events reproduce my local numbers (155.6 Hz envelope 0.0276 → 0.0175 → 0.0110 → 0.0083).

| dataset (note) | sample | env −50 ms | at | +50 ms | max 20 ms rise within ±40 ms | largest rise in the 3 s window |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| constructed (51) ×4 | 7,210,303–7,211,007 | 0.026–0.028 | 0.016–0.017 | 0.011 | 0.89–0.92 | 6–12×, 755–760 ms earlier |
| physical-highmid (56) | 990,399 | 0.0170 | 0.0155 | 0.0144 | 0.97 | 13×, 815 ms earlier |
| physical-high (60) | 1,679,935 | 0.0248 | 0.0240 | 0.0238 | 1.00 | 18×, 725 ms earlier |
| physical-high (60) | 2,055,615 | 0.0276 | 0.0257 | 0.0239 | 0.97 | 20×, 475 ms earlier |

**Reading.** At all seven suppressed NoteOns the same-pitch envelope is flat or decaying (no 20 ms rise above 1.0×),
while each window holds a real attack 0.5–0.8 s earlier, which the stable path keeps. So none of the seven is an acoustic
re-pluck at the nominal pitch; the stable note carrying through is correct for them. Limits: nominal-pitch single band
(detuned or inharmonic re-plucks could hide), 7 events of one kind, not the ordinary recording (1,614 pairs; 58 inside the
annotation attack zone remain untested acoustically). The corpus gate for `acoustic_repluck_preservation` stays "not
measured" until an attack-specific test covers re-plucks that the baseline did emit. No exemption, gate, policy or default change.
