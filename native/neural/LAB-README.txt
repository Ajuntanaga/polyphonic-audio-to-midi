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

This is a research artifact, not the installed M3 tracker or an accepted
replacement. Corpus label losses remain; external DAW/device operation and
reliable live use are unverified. Keep both bundled license notices.
