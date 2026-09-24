# Changelog

## [0.1.0-beta.2] - 2026-09-24

### Added

- Linux x86-64 VST3 release bundle with the custom resizable tuner editor.
- Eight string-aware tuner lanes, per-string calibration, and single-channel or
  per-voice MIDI routing.
- Automated source, native C++, and CodeQL workflows for public changes.

### Fixed

- REAPER launch tools now accept `--reaper`, honor `M3_REAPER`, search `PATH`,
  and use `$HOME/opt/REAPER/reaper` only as the final fallback.
- Fresh-clone instructions now initialize the pinned VSTGUI submodule.
- Public documentation uses generic audio-interface wording outside identifiers
  that must remain exact.

### Known limits

- Physical eight-string tracking remains beta and still needs broader recorded
  instrument validation.
- The release currently targets Linux x86-64 and REAPER.

## [0.1.0-beta.1] - 2026-09-23

- First public source prerelease.
