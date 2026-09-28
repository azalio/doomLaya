---
language:
- en
license: apache-2.0
library_name: laya
base_model: convaiinnovations/laya
base_model_relation: finetune
tags:
- doom
- vizdoom
- supervised-fine-tuning
- imitation-learning
- decision-making
- modernbert
---

# Laya Doom v0.3.1: MAP01–MAP03

One fixed Laya bundle completed FreeDoom MAP01, MAP02 and MAP03 without
deaths in one sequential real-time series. The model chooses the action,
target, weapon and combat movement. The controller routes, aims and presses
buttons to execute those choices.

| Map | Seed / skill | Exit time | Deaths | Full-decision HTTP p50 / p90 |
|---|---|---:|---:|---:|
| MAP01 → MAP02 | 48 / 3 | 168.400 s | 0 | 266.01 / 288.46 ms |
| MAP02 → MAP03 | 54 / 3 | 420.400 s | 0 | 295.81 / 337.32 ms |
| MAP03 → MAP04 | 54 / 3 | 347.114 s | 0 | 309.47 / 367.67 ms |

Recorded on macOS/MPS, float32, 35 game ticks per second. Every recording
includes 105 ticks of the next map. Video, real-time pacing and model authority
checks passed. MAP02 and MAP03 also passed navigation thresholds. MAP01
retains a warning: 32.23 seconds without a new region exceeds the 25-second
threshold, so its overall quality check remains false.

These maps and seeds were used during development. This is one final series
after multiple failed experiments, not an independent generalization or
reliability benchmark. Actual RTT is included; responses are applied as soon
as received, without the older artificial minimum delay of 16 ticks.
There were no external model API calls. Local compute and training cost were
not estimated. This release has no new Jev comparison.

[Videos and telemetry](https://github.com/azalio/doomLaya/releases/tag/v0.3.1) ·
[Verification and hashes](https://github.com/azalio/doomLaya/blob/v0.3.1/reports/v031-regression.json) ·
[Reproduction and training](https://github.com/azalio/doomLaya/blob/v0.3.1/docs/REGRESSION-FIX.md).

## Architecture and training

The eight checkpoints share one identical frozen encoder at inference.
Question names select the trained head. Command, item, combat movement and
mechanism heads also use learned numeric residual networks over observed
facts. Their weights and feature specifications are covered by the model
manifest. This is an architecture extension and supervised adaptation of
Laya, not the unchanged upstream model.

Training uses recorded game observations, labels from offline policies,
synthetic examples, and retention of previous model decisions. This is
supervised imitation learning / behavior cloning, with no reward-based RL.
The offline policies are not called by the game or inference server.
Training and validation are correlated same-map development data.

The final command repair updates existing numeric layers while retaining
all 1096 recorded decisions from earlier successful MAP01/MAP03 runs.
The selected epoch is 65 of 1600; validation labels match in 1179/1191 cases.
These numbers are training diagnostics, not gameplay success rates.

Bundle manifest:
`74eea1043aa584bf825fe25ac40be5fc7affc555c63dea8712b9b807ae9cafb6`.
Use `question-heads.json` and `SHA256SUMS` to verify the files.
`training-assets/` contains the parent checkpoints, semantic caches and
retention traces for the documented final training stages. It is optional
for inference. Training datasets and scripts are in the GitHub release tag.

Base: `convaiinnovations/laya/typed-decisions` at
`1c5edc17a7acd8701df6fc341c0d179f1c62c982`; Laya source commit
`42626c348753fbb17572a813127df2278a1ec527`. Apache-2.0; see `NOTICE`.

## Download

Install the repository and dependencies using the linked reproduction guide.
From its root directory:

```bash
hf download azalio/laya-doom-map03 --revision v0.3.1 \
  --exclude 'training-assets/*' --local-dir checkpoints/laya-doom-v031
(cd checkpoints/laya-doom-v031 && shasum -a 256 -c SHA256SUMS)
```

The guide includes the exact server flags, three-map regression command,
and training commands with the published dependencies. The v0.3.0 tag
preserves the previous release, whose MAP01/MAP02 regression failed.
