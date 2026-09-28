# doomLaya

[English](README.en.md) · [Русский](README.md) — this file is the English version.

Laya and Jev play FreeDoom. The model picks the action, target and weapon;
the controller builds the route, aims and presses buttons on its command.

[Training](docs/TRAINING.en.md) · [Results](docs/COMPARISON.en.md) ·
[Weights and publishing](docs/PUBLISHING.en.md) · [Control contract](docs/DOOM.en.md)
(Russian originals: [TRAINING](docs/TRAINING.md), [COMPARISON](docs/COMPARISON.md),
[PUBLISHING](docs/PUBLISHING.md), [DOOM](docs/DOOM.md))

## v0.3.1: MAP01–MAP03 regression fix

One fixed checkpoint bundle completed MAP01 in 168.400 s, MAP02 in
420.400 s and MAP03 in 347.114 s, with no deaths. Each recording includes
three seconds of the next map. The controller executes model decisions.
Responses are applied when received; actual RTT remains measured.
MAP01 retains a navigation warning: 32.23 s without a new region against
a 25 s limit. This is one final series on the development seeds.
[Reproduction and training (Russian)](docs/REGRESSION-FIX.md) ·
[Verification and recording hashes](reports/v031-regression.json).

[v0.3.1 weights](https://huggingface.co/azalio/laya-doom-map03/tree/v0.3.1) ·
[MAP01 video](https://github.com/azalio/doomLaya/releases/download/v0.3.1/laya-map01.mp4) ·
[MAP02 video](https://github.com/azalio/doomLaya/releases/download/v0.3.1/laya-map02.mp4) ·
[MAP03 video](https://github.com/azalio/doomLaya/releases/download/v0.3.1/laya-map03.mp4).

## v0.3.0: MAP03 → MAP04

Laya completed MAP03 in 819.914 s: seed 54, skill 3, four deaths.
The recording includes three seconds on MAP04. Model-authority and recording
checks passed. The overall quality gate failed: stationary time reached
141.83 s. This is one successful development run. In the
[regression check](docs/REGRESSION-v0.3.0.md), this checkpoint set failed to
complete MAP01 within 180 s and MAP02 within 1800 s on the previous seeds.
Jev has not been tested on MAP03.

[Weights](https://huggingface.co/azalio/laya-doom-map03/tree/v0.3.0) ·
[Setup and training (Russian)](docs/MAP03.md) ·
[Video with telemetry](https://github.com/azalio/doomLaya/releases/download/v0.3.0/laya-map03.mp4) ·
[Verification report](reports/map03-success.json).

## v0.2.0: MAP01 and MAP02

The same checkpoint set and executor completed MAP01 in 174.914 s (seed 48,
no deaths) and MAP02 in 835.600 s (seed 54, two deaths), both at skill 3.
Each recording includes three seconds on the next map. Model-authority,
video and real-time checks passed. The overall quality gate remains false:
MAP01 exceeded stationary and region-progress limits; MAP02 exceeded the
region-progress and weapon-switch limits. These are single development runs.

[Weights](https://huggingface.co/azalio/laya-doom-map02) ·
[Setup and training (Russian)](docs/MAP02.md) ·
[Videos and evidence](https://github.com/azalio/doomLaya/releases/tag/v0.2.0).
The older v3/Jev comparison below uses a different executor and request format.
It does not compare the new checkpoint set against Jev.

## v0.1.0 comparison on MAP01

Compared on 22 September 2026 on macOS/MPS: FreeDoom MAP01, difficulty
`skill 3`, random seed `seed 48`. Both models share one executor,
asynchronous requests and a 35 ticks/s game speed.

| Model | Result | HTTP p50 incl. RTT | API cost |
|---|---|---:|---:|
| Original Laya typed-decisions | Did not finish in 180 s | 106 ms | $0 |
| Laya, adaptation v3 | **MAP01 → MAP02 in 61.43 s** | 108 ms | $0 |
| Jev 1.13 | **MAP01 → MAP02 in 68.97 s** | 357 ms | $0.004580184 |

Both successful runs with no deaths. Laya picked up resources, acquired and used
the shotgun. Laya was fine-tuned for this task, Jev was not. One final seed
and one map were verified; they do not prove general model superiority.
Local compute and training costs were not estimated.

Measurements, completion checks and video SHA-256 — in [reports](reports).
[Video: Laya v3 and Jev](https://github.com/azalio/doomLaya/releases/download/v0.1.0/laya-vs-jev.mp4) ·
[Video: original Laya and Jev](https://github.com/azalio/doomLaya/releases/download/v0.1.0/original-laya-vs-jev.mp4) ·
[Model on Hugging Face](https://huggingface.co/azalio/laya-doom-v3) · [Weights archive](https://github.com/azalio/doomLaya/releases/tag/v0.1.0).
Download commands — in [PUBLISHING.md](docs/PUBLISHING.en.md).

## Setup

You need Python 3.12+, Git, [uv](https://docs.astral.sh/uv/) and `ffmpeg` in PATH.
On macOS: `brew install uv ffmpeg cmake boost sdl2 openal-soft`. On Ubuntu,
install `cmake`, `libboost-all-dev`, `libsdl2-dev` and `libopenal-dev` for the build.
Clone the repository and install the environment.

```bash
git clone https://github.com/azalio/doomLaya.git
cd doomLaya
uv venv --python 3.12
uv pip install --python .venv/bin/python -r requirements-lock.txt
uv pip install --python .venv/bin/python -r requirements-model.txt
.venv/bin/python scripts/install_vizdoom_sector_fix.py
```

`requirements-model.txt` is needed for local Laya and training; for Jev alone
the first file is enough. The Laya source version is pinned by commit SHA.
Base weights are fetched from Hugging Face at a fixed revision, with no
dependency on someone else's checkout or home directory.

## Running the original Laya

In the first terminal:

```bash
.venv/bin/python serve_doom_laya.py --model typed-decisions --device auto
```

The first run downloads `typed-decisions` from `convaiinnovations/laya`.
In the second terminal, from the same directory:

```bash
.venv/bin/python agent.py --model typed-decisions --seed 48 \
  --seconds 180 --record auto --show --stop-after-level
```

The original model did not finish the level in the final experiment. To reproduce
a successful run you need the adaptation weights below.

## Running adaptation v3

Download the full model directory into `checkpoints/laya-doom-v3`:

```bash
.venv/bin/hf download azalio/laya-doom-v3 \
  --revision d27276e3bf8275cdbc9a7a72d80cad656aa87bd7 \
  --local-dir checkpoints/laya-doom-v3
(cd checkpoints/laya-doom-v3 && shasum -a 256 -c SHA256SUMS)
```

Other options: [archive from GitHub Release](docs/PUBLISHING.en.md) or
[train your own model](docs/TRAINING.en.md). A `git clone` command downloads sources without weights.

```bash
.venv/bin/python serve_doom_laya.py \
  --checkpoint checkpoints/laya-doom-v3 --device auto --port 8001
```

In the second terminal:

```bash
.venv/bin/python agent.py --model doom-adapted --seed 48 \
  --seconds 180 --record auto --show --stop-after-level
```

`--device auto` picks CUDA, then MPS, then CPU. For an exact match with
the original experiment use `--device mps`. CPU and CUDA are supported in code;
a full playthrough on them was not separately verified. For a headless run drop `--show`.
A normal start is the standard FreeDoom inventory. The WAD ships with ViZDoom.

## Jev and comparison

Create a local `.env` if you do not have one yet, and add your OpenRouter key:

```bash
test -e .env || cp .env.example .env
chmod 600 .env
```

The client reads `OPENROUTER_API_KEY` automatically. Do not commit `.env` to Git.

```bash
.venv/bin/python agent.py --model jev --seed 48 \
  --seconds 180 --record auto --show --stop-after-level
```

For three sequential runs, start both local servers
(original on 8000, adaptation on 8001), then:

```bash
.venv/bin/python -m tools.run_comparison --seed 48 --seconds 180
```

In the `SUITE` line the script prints the results directory. The path of each run
is in the `path` field of the next JSON record; the `RUN` line is kept in its log.
API errors have no fallback strategy. If the player did not finish the level, the completion check returns FAIL,
even if the executor correctly carried out all model commands.

```bash
.venv/bin/python -m tools.render_comparison runs/<laya-run> runs/<jev-run> \
  --output runs/laya-vs-jev.mp4
.venv/bin/python -m tools.measure_network runs/network.json
```

The video shows two windows: HP, ammo, kills, command, target, weapon,
choice probabilities, state age and API price.
Full HTTP request time includes RTT — network round-trip time.
The game keeps running during the request; windows are synced by game time. When a run finishes,
its last frame stays on screen with a caption.

## Responsibility boundary

The model receives a text state and two questions: `command`, `weapon`.
Command options include specific visible monsters and observed items.
The executor can aim, walk to the given target and route around obstacles.
It does not choose item utility, combat priority or the best weapon.

Both models get the WAD geometry and the exit position. `exit` routes
to the exit; an intermediate door needs a separate `open_door`. `explore` is a
movement macro toward the nearest unvisited area. The experiment compares command choice from text state. It does not test
neural control of every button or image-only play.

An item may be picked up accidentally on the way by the engine itself. Weapon auto-switch on
pickup is disabled. An unreachable command is temporarily excluded after a real
pathfinding failure and returns after a position/door change.
Responses older than two seconds and responses from another episode are not applied.
After a real MAP01 completion, MAP02 starts with a standard inventory;
`--stop-after-level` records three more seconds and stops.

## Verification

```bash
.venv/bin/python -m unittest tests.test_authority tests.test_publication
.venv/bin/python scripts/check_publication.py
.venv/bin/python -m tools.check_authority runs/<run>
.venv/bin/python -m tools.verify_run runs/<run>
```

Each recording keeps requests/responses, events, per-frame telemetry,
video, config and a copy of the game sources with hashes.
`execution.decision_id` links buttons to a specific model response.
Before publishing, setup, 16 tests,
one training step and a five-second play with the packaged weights were verified in a clean environment.
[Validation protocol](reports/publication-validation.json). Full training and
playthrough were not re-run while preparing the archive.

GitHub Actions runs source checks without an API key or large weights;
training and full game playthroughs do not run in CI.

## License and sources

Code and adaptation — [Apache-2.0](LICENSE); attribution — [NOTICE](NOTICE).
Based on: [Laya](https://github.com/NandhaKishorM/laya),
[ViZDoom](https://github.com/Farama-Foundation/ViZDoom),
[FreeDoom](https://freedoom.github.io/),
[Jev via OpenRouter](https://openrouter.ai/typesafe/jev-1.13).
The experiment idea came from a user-provided post from the
[prompt_design](https://t.me/prompt_design) channel; original third-party materials
and historical drafts are not included in the publication.
