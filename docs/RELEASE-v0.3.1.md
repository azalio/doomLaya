# v0.3.1: one Laya bundle completes MAP01–MAP03

The same eight-head bundle completed all three FreeDoom maps without deaths
in one sequential real-time series. Each video includes three seconds of
the next map, telemetry and measured decision latency.

| Map | Seed / skill | Exit | Deaths | HTTP p50 / p90 |
|---|---|---:|---:|---:|
| MAP01 → MAP02 | 48 / 3 | 168.400 s | 0 | 266.01 / 288.46 ms |
| MAP02 → MAP03 | 54 / 3 | 420.400 s | 0 | 295.81 / 337.32 ms |
| MAP03 → MAP04 | 54 / 3 | 347.114 s | 0 | 309.47 / 367.67 ms |

Completion, video, real-time pacing and model-authority checks passed.
MAP01 still exceeds one navigation threshold: 32.23 s without a new region
against a 25 s limit. Its overall quality check remains false.
The maps and seeds were used during development; this single final series
does not establish reliability on unseen runs. Failed experiments remain
documented. No new Jev comparison was run.

The model selects actions, targets, weapons and combat movement. The controller
executes those choices. The fix includes learned numeric heads for commands,
items, movement and mechanisms, supervised corrections for enemy and weapon
heads, and correct exit-switch approach. Responses now apply when received;
the regression runner defaults to zero artificial minimum delay while
preserving real RTT and game time.

[Weights and training dependencies](https://huggingface.co/azalio/laya-doom-map03/tree/v0.3.1) ·
[Run and train (Russian)](https://github.com/azalio/doomLaya/blob/v0.3.1/docs/REGRESSION-FIX.md) ·
[Full verification](https://github.com/azalio/doomLaya/blob/v0.3.1/reports/v031-regression.json).

Training uses supervised imitation learning with recorded observations,
offline labels, synthetic examples and retention of earlier decisions.
The final command training was repeated from the packaged dependencies;
its model, numeric weights and feature specification match byte for byte.
Earlier training stages were not all repeated for this release.

Assets include three full videos, per-map evidence archives and `SHA256SUMS`.
Archives contain decisions, telemetry, events, verification and the source
snapshot used for each run. Local paths in JSON metadata are sanitized;
`evidence-files.json` records original and published hashes. Videos are
separate from the archives. Source and training datasets are in this Git tag;
model weights and parent checkpoints are on Hugging Face.
