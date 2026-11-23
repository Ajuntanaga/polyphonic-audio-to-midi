# Audio envelope at the four suppressed NoteOns of constructed labels 112–115 (POST HOC)

User asked for audio tests. The only local recording covering any of the seven labels is the constructed one
(`combinations.wav`, int16, 96 kHz); the physical-highmid/high recordings and the ordinary waveform are not on this
machine (only inside the remote input bundle), so labels 2/3/4 and the ordinary recording were not tested.
Not pre-registered; one run, output in `CLAUDE-M3-CONSTRUCTED-AUDIO-ENVELOPE-20261122.txt`.

Method: band-pass ±3% around 155.56 Hz (MIDI 51), 5 ms mean Hilbert envelope, around the label (start 7,142,453).

- The four removed NoteOns sit at samples 7,210,303–7,211,007: 706–714 ms after the label start, spanning 704 samples (7.3 ms)
  with channel flips 0→2→0→2→0. Four attacks of one string in 7 ms are not physical.
- The 155.6 Hz envelope at those samples is **decaying**: 0.0276 (−50 ms), 0.0175 (event), 0.0110 (+50 ms), 0.0083 (+300 ms).
- The largest 20 ms envelope rise inside the label (1.62×) is at 335 ms after the annotated start, not at the events;
  within ±20 ms of the events the envelope varies by 1.5×, inside the label-wide 10 ms-window median 1.28 and max 2.33.

**Reading:** for constructed labels 112–115 the suppressed NoteOns are lane flicker over a sustained, decaying note, not
acoustic re-plucks; the stable note carrying through is the correct output. Single-band energy check only (no
transient/onset model; polyphonic mix of real excerpts). This does NOT cover physical-highmid 2 or physical-high 3, 4:
those need their recordings, which are in the remote bundle. A GHA job on the worker could run this same envelope test
there with no download; that is Codex's worker and has not been started. No exemption, gate, policy or default change.
