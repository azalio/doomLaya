# doomLaya v0.2.0 — MAP01 and MAP02 completion

A five-head Laya checkpoint set with a shared encoder is now available. The model
chooses actions, targets, weapons and combat movement; the executor applies them.

| Map | Seed, skill | Exit | Deaths | Full decision p50 |
|---|---|---:|---:|---:|
| MAP01 → MAP02 | 48, 3 | 174.914 s | 0 | 384.72 ms |
| MAP02 → MAP03 | 54, 3 | 835.600 s | 2 | 430.47 ms |

Each recording includes three seconds on the next map. Model-authority, video
and real-time checks passed. The overall `passed=false` is retained because
movement limits, and on MAP02 the weapon-switch limit, were exceeded. These are
single runs on development maps, not evidence of robustness across seeds.

- [Weights on Hugging Face](https://huggingface.co/azalio/laya-doom-map02/tree/v0.2.0).
- [Setup, frozen data and training instructions (Russian)](https://github.com/azalio/doomLaya/blob/v0.2.0/docs/MAP02.md).
- Full recordings: `laya-map01.mp4`, `laya-map02.mp4`; last 65 seconds: `laya-map02-finish.mp4`.
- `map01-evidence.tar.gz` and `map02-evidence.tar.gz` contain telemetry,
  model requests/responses, events and the exact run source snapshots. To audit,
  extract an archive, put the matching recording inside as `video.mp4`, and run
  `.venv/bin/python -m tools.verify_run <run-directory>`.
- Verify release assets using `SHA256SUMS`.

The code follows the merged `doomlib/`, `tools/`, `tests/` and `docs/` layout and
preserves Windows UTF-8 fixes. A pinned ViZDoom patch fixes the sector-line
buffer overflow when loading MAP03 without changing the WAD or game rules.
The v0.1.0 weights and recordings remain available. Its Jev comparison used
the previous model and executor configuration.
