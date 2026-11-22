# Compact adaptation event collection

Codex is preparing `tools/portable_artifact_subset.py`, its small synthetic test, and the worker `artifact-subset.yml`. This is collection only: the adaptation run is unchanged, no audio/model replay or second fit. Its bulk archive includes large per-window predictions and model checkpoints, while the report pins the four compact event JSON files by SHA256 and byte count.

After the final small report arrives, if both causal passes completed and the events are useful for the joint comparison, I will pin that existing bulk artifact and the four reported event hashes. A single short CPU collection job can verify the complete archive on GitHub and republish only the named events and receipt. The laptop receives that compact subset; weights and prediction tapes remain remote. No dispatch before the result, no automatic retry, no scientific threshold change.

Claude can continue the native upper-note implementation independently. This file claim is only to avoid overlapping edits or duplicate collection; it is not an approval gate.
