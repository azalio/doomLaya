# Laya and Jev: decisions belong to the models

[English](COMPARISON.en.md) · [Русский](COMPARISON.md) — this file is the English version.

[Video: Laya v3 and Jev](https://github.com/azalio/doomLaya/releases/download/v0.1.0/laya-vs-jev.mp4) ·
[Video: original Laya and Jev](https://github.com/azalio/doomLaya/releases/download/v0.1.0/original-laya-vs-jev.mp4).
[Model on Hugging Face](https://huggingface.co/azalio/laya-doom-v3) · [Release with weights archive](https://github.com/azalio/doomLaya/releases/tag/v0.1.0).
[Publishing and download](PUBLISHING.en.md) · [Measurements summary](../reports/comparison.json)

On MAP01, skill 3, seed 48 the original Laya did not finish
the level in 180 seconds. After adaptation Laya finished the level in 61.43 s,
Jev — in 68.97 s. Both entered MAP02, with no deaths.
This is one final seed and one map: it does not prove general superiority of the adapted model
over Jev. Laya was trained on this task; Jev was not.

| Model | MAP01 exit | Kills | Deaths | HTTP p50 / p95, ms | Run API cost |
|---|---:|---:|---:|---:|---:|
| Original Laya | did not finish in 180 s | 5 | 0 | 106 / 124 | $0.000000 |
| Laya, adaptation v3 | 61.43 s | 12 | 0 | 108 / 133 | $0.000000 |
| Jev 1.13 | 68.97 s | 13 | 0 | 357 / 445 | $0.004580 |

Jev cost is $0.004580184: the sum of `usage.cost` over 139 responses.
It covers the whole shown run plus the last three seconds of MAP02, but no
earlier diagnostics. Laya has no external API charge; hardware,
electricity and training costs were not converted to money. OpenRouter price at check time: $0.042 per million input tokens, outputs free.
[Model pricing](https://openrouter.ai/typesafe/jev-1.13).

## Who decides what

The model picks the action, the specific monster or item, and the weapon. The executor
can aim, build a route to the given target and press the chosen buttons.
It does not pick combat priority, item priority, exit priority or the best weapon.
The `wait` command does not turn into combat; `exit` does not collect items on purpose and
does not open an intermediate door. `USE` for such a door requires `open_door`.

The navigator has the WAD geometry and the exit position. This is the same help for both
models. Visible monsters come from labels, items from observations and memory.
The Doom engine picks up an item on coordinate overlap, so the player
may get an item accidentally on the way.
Weapon auto-switch on pickup is disabled; ATTACK during a switch is forbidden.

After confirmed unreachability, a pickup command temporarily disappears from the
executable command list until a position/door change. This is an executability limit,
not a usefulness filter. Useful items and weapons are chosen by the model.
The sensor cross-checks doors against WAD manual-door specials.
Sector 208, previously misclassified as a door, is not offered to the model.

## RTT and real speed

The game runs at 35 ticks/s, requests are asynchronous, at most one per 0.5 s.
Waiting for the model does not pause the game; the previous command applies with a 2 s TTL.
Other-episode and stale responses are not executed.

The table shows full HTTP request time: payload transfer, network and processing.
Median time from state observation to applied response:
Laya v3 115 ms, Jev 371 ms.
A separate measurement to OpenRouter: TCP handshake about
22.8 ms, TLS 156.5 ms,
plain HTTP without inference 110.6 ms.
TCP estimates RTT to the service edge, not to the provider GPU. Subtracting plain HTTP
from the game request does not give exact model compute time.
[Raw network measurements](../reports/network.json).

In all three final runs wall-clock time matched
game time. An early run,
in which repeated pathfinding to an unreachable goal slowed the simulation, was excluded from the RTT comparison.
The video is synced by game time, 2560×1440, 35 fps, no speed-up.
The side that finished first stays on its last frame with an explicit caption.

## What changed in Laya

Laya sources checked at commit `42626c348753fbb17572a813127df2278a1ec527`: `agent.py`, `common.py`, `serve.py`
and the training notebook. Selection uses argmax; temperature does not fix the chosen
class. The compact `patrol` history hurt the original setup. CPU and MPS gave
identical classes on five separately checked problem states.

Original weights and the port-8000 server are untouched. The adaptation is a separate saved model
`checkpoints/laya-doom-v3`, server on 8001. In v1/v2 the decision head was trained,
in v3 the last three encoder layers too. Training seeds 42/43, epoch selection on 44;
the final game seed 48 is not in training.

v3: 979 training decisions and 130 validation decisions; labels were set by
game rules before training. On this check — 72.5% commands and 98% weapons. These percentages
show the share of correct answers, not the playthrough probability. Weights:
`bb9083189517c5dc5c0e357062446df2ea73eadc3d909ec6ec7a6cee222a6147`.

## Previous iteration

Before the final fixes, adaptation v2 did not pass seed 46 in 180 seconds;
Jev passed it in 51.49 s. That recording is kept locally and is not part of the final release files. Afterwards, approach-through-obstacle and false-door bugs were fixed,
and v3 got extra training. Results across versions are not averaged.
An interrupted diagnostic run on seed 47 does not count as a completed trial.

## Behavior check

Adapted Laya killed 12 monsters, picked up the shotgun
and fired it: 73 ticks with ATTACK.
Resource gains: HP +24, armor
+103, bullets +15,
shells +8.
Longest out-of-combat stop — 1.63 s;
in-place direction changes — at most
2 per second.

`tools/check_authority.py` matches each frame's buttons against the accepted model response.
`tools/verify_run.py` additionally checks the engine-confirmed MAP02 transition, video,
tick continuity, game speed and navigation limits. The Laya v3 and Jev runs
passed the check; the original Laya run got FAIL. All sources and hashes are stored
in the run's `source/` directory.

[Machine summary](../reports/comparison.json) · [Reproduction commands](../README.en.md).

The old result with six wins of the general strategic controller is kept
in `archive/controller-baseline/` and `runs/20260921_223707_paired-levels/`.
It is not used to claim that models can choose actions on their own.
