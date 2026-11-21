M3 Neural Lab (96 kHz) -- uninstalled experimental Linux VST3

Requires 96,000 Hz, real-time processing, and host blocks of 1..1024 samples.
Accepts mono or stereo; dry audio is unchanged. Stereo analysis uses the mean.
Pitch MIDI uses channel 1 with constant velocity 100. No string assignment,
MPE, pitch bends or same-pitch unison multiplicity is implemented.

The model runs on a separate CPU worker with bounded queues. Output events
are delivered at offset zero in the next available host callback. Reported
plugin latency is zero for dry audio; it is not a claim of zero MIDI latency.
Panic releases accepted notes and resets worker state. After a worker failure,
deactivate and reactivate the component. A host refusing output prevents new
notes until Panic and successful cleanup; accepted notes remain owed releases.

Quiet input gate is optional and OFF by default. Its threshold defaults to
-60 dBFS (adjustable -90..-30 dBFS); reopening requires 6 dB more level.
It uses the larger trailing 20/80 ms input power and a 40 ms quiet dwell.
Closing releases tracked notes at the next model readout and blocks new notes
until the input rises again. The model keeps processing the continuous input.
This can remove weak sustains as well as false notes in silence. Adjust it to
your input level; it does not distinguish a quiet intended note from noise.
Controls take effect on a source packet boundary, then worker/host delivery;
they are not sample-accurate and do not discard already queued output. Use
Panic for immediate accepted-note cleanup. Settings are saved with the plugin.

This is a research artifact, not the installed M3 tracker or an accepted
replacement. Corpus label losses remain; external DAW/device operation and
reliable live use are unverified. Keep both bundled license notices.
