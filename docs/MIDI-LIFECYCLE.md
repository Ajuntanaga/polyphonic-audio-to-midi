# MIDI lifecycle and cleanup boundary

The production JSFX emits ordinary channel MIDI for a downstream VSTi. It does
not use MPE and does not consume incoming MIDI. Detector audio can pass through
unchanged or be muted after the detector has copied the selected left, right,
or equal-power downmix signal.

## Ordered real-time path

Voice evidence is selected once per audio block and passed through independent
OFF, ATTACK, ON, and RELEASE states for all 128 MIDI pitches. No more than eight
pitches can be active. Each committed transition occupies one of sixteen fixed
event cells; note-offs take priority if that queue reaches capacity.

At the start of each block the event and emission cursors are reset. The audio
sample path sends each committed event exactly once. MIDI channels are clamped
to 1 through 16, note-ons use `0x90 | channel`, and note-offs use
`0x80 | channel` with velocity zero. Event offsets are clamped to
`0..samplesblock-1`. The current detector commits at a block boundary, so its
normal production events truthfully use offset zero; there is no lookahead or
declared PDC.

This design adds the host block plus the configured attack evidence to onset
latency. Smaller audio blocks reduce the host portion. The response control
trades faster commitment for additional stability; it does not allocate memory
or rebuild the detector in the sample path.

## Reachable cleanup

The JSFX can clean up whenever REAPER continues calling it. At a block boundary
it detects these conditions:

- sample-rate change;
- transition from playing or recording (`1` or `5`) to stopped or paused
  (`0`, `2`, or `6`);
- detector input, mode, A4, pitch range, polyphony, M3 fret limit, or MIDI
  channel reconfiguration;
- the explicit Panic control.

For every reachable condition, all active pitches are sent as note-offs at
offset zero on the previously active MIDI channel before detector memory is
reset. The reset clears conditioner, resonator, salience, selection, M3 scratch,
voice, and event state. New settings are then applied at the same block
boundary. Slider callbacks only clamp and stage settings; they never rebuild
real-time memory.

The input gate refuses selection below the fixed `1e-8` fast-energy floor. An
explicit Panic also latches detection off until a subsequent block's input peak
falls below `0.0001`. This prevents the same still-ringing block from refilling
detector and lifecycle state immediately after cleanup.

## Abrupt boundary

No JSFX can send cleanup MIDI after its callbacks have stopped. Abrupt raw FX
bypass, FX removal, project termination, host failure, or a device failure that
halts processing can therefore strand a downstream note if REAPER does not
flush MIDI itself.

The verified Safe Bypass ReaScript covers the deliberate detector-bypass path
while REAPER is still processing. It requires one selected track and exactly
one matching detector, records that detector's GUID and sensitivity, prevents
new detections, requests Panic, waits 50 ms for note-off delivery, disables the
same detector, and restores sensitivity while it remains disabled. It never
deletes an FX. If identification, Panic, or disable verification fails, it
reports the failure and does not continue as if bypass succeeded.

That script is not protection against a host crash, power loss, device failure,
force removal, or any event that stops callbacks before Panic can be delivered.
The downstream VSTi should still expose an independent All Notes Off/Panic
control for those abrupt conditions.

## Current validation boundary

Cases 9101 through 9109 exercise encoding, offset bounds, sample-rate and
transport cleanup, explicit Panic, duplicate-note prevention, input selection,
and mode-bound staging through the shared production module. Task 11 then ran
the disposable Signal Source -> production detector -> MIDI Capture ->
ReaSynth -> Synth Output Probe chain. Ten eight-note Panic trials passed with
all note-offs in `1.750–5.333 ms`; the final trial executed the actual Safe
Bypass file inline and verified disable before the disposable runner's separate
delete gate.

This validates synthetic VSTi routing and deliberate safe bypass. It does not
constitute live-guitar, audio-interface, audible-output, host-crash, or
performance-readiness evidence.
