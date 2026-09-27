# doomLaya v0.3.0 — MAP03 completion

Laya completed FreeDoom MAP03 in 819.914 s (seed 54, skill 3), after four deaths.
The full 822.943 s recording includes 106 frames on MAP04. Model-authority,
video completeness and real-time checks passed: 28,803 frames and 1,595 accepted
decisions. The overall quality gate remains false: stationary time reached
141.83 s, and time without a new region reached 159.29 s.

This is one successful development run, not a robustness estimate. MAP01 and
MAP02 have not been revalidated with these MAP03 weights. Jev was not tested
on MAP03. HTTP latency including RTT: p50 342.52 ms, p90 406.70 ms; minimum
application delay 16 ticks, observed p50 457.143 ms. External API cost was $0;
local training and compute cost were not estimated.

- [Exact eight-checkpoint bundle](https://huggingface.co/azalio/laya-doom-map03/tree/v0.3.0).
- [Setup, frozen datasets and training commands](https://github.com/azalio/doomLaya/blob/v0.3.0/docs/MAP03.md).
- Full video: `laya-map03.mp4`; last 65 seconds: `laya-map03-finish.mp4`.
- `map03-evidence.tar.gz` contains telemetry, model requests/responses, events,
  verification results and the exact gameplay source snapshot. Extract it,
  put `laya-map03.mp4` inside as `video.mp4`, and run
  `.venv/bin/python -m tools.verify_run <run-directory>`.
- Check all assets against `SHA256SUMS`. An exit code of 1 from `verify_run`
  is expected for this recording: the mission passed, but navigation quality failed.

The new heads were trained using supervised imitation learning from recorded
states, offline expert labels and synthetic contrasts. The encoder was frozen;
there was no reward-based RL. The live controller executed model choices.
The code also handles MAP03 mechanisms and changing floor geometry, and records
decision application delay. Earlier v0.1.0 and v0.2.0 releases remain available.
