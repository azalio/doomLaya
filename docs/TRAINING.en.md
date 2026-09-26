# Training Laya for FreeDoom

[English](TRAINING.en.md) · [Русский](TRAINING.md) — this file is the English version.

The script saves the trained model into a separate directory — a checkpoint.
The original Laya weights are never overwritten. Training uses pre-labelled
examples: labels encode game rules, and at play time the model makes the decisions.

## 1. Prepare the environment and data

From the repository root:

```bash
uv venv --python 3.12
uv pip install --python .venv/bin/python -r requirements-lock.txt -r requirements-model.txt
.venv/bin/python training/finetune.py --data training --validate-only
.venv/bin/python training/finetune.py --data training/v3 --validate-only
```

Training-example JSON files are included in the repository. Their versions are frozen,
so old game recordings are not needed to repeat training. Hashes and provenance — [training/datasets.json](../training/datasets.json).

| Stage | Train questions | Validation questions | Game seeds |
|---|---:|---:|---|
| v1/v2 | 427 | 130 | train 42/43, validation 44 |
| v3 | 979 | 130 | train 42/43, validation 44 |

Each row holds one `command` or `weapon` question.
Row fields: `state`, `question`, `label`, `kind`, category, source run,
tick and a state-augmentation flag. Low-HP states,
zero-ammo states and states with the shotgun already held were added; rare-door examples were repeated in the training split.
The split is by source run, not by random neighbouring frames.
All examples are MAP01. The final seed 48 is not in training,
but the map geometry is the same: transfer to an unseen level was not tested here.

The data holds states from a previous game controller; expert labels were
assigned offline. These recordings serve as training examples but do not prove that the old model
made decisions on its own. The v1/v2 and v3 JSON files are frozen separately. The query format changed between iterations,
so newly generated data from the current code does not replace them.

## 2. Train v1 → v2 → v3

The commands below create new directories with a `-repro` suffix to keep
the released weights intact. The script refuses to run if the `--output` directory already exists.
The first stage downloads the `convaiinnovations/laya/typed-decisions` base at revision
`1c5edc17a7acd8701df6fc341c0d179f1c62c982`.

```bash
.venv/bin/python training/finetune.py \
  --data training --epochs 4 --lr 0.00003 --device mps \
  --output checkpoints/laya-doom-head-v1-repro

.venv/bin/python training/finetune.py \
  --base checkpoints/laya-doom-head-v1-repro \
  --data training --epochs 6 --lr 0.0003 --device mps \
  --output checkpoints/laya-doom-head-v2-repro

.venv/bin/python training/finetune.py \
  --base checkpoints/laya-doom-head-v2-repro \
  --data training/v3 --epochs 5 --lr 0.0001 --encoder-last 3 --device mps \
  --output checkpoints/laya-doom-v3-repro
```

On CUDA replace `--device mps` with `--device cuda`; for CPU use `cpu`.
Auto-select is `auto`. The measured v3 stage on MPS took about 507 seconds;
other devices may differ. Each saved model
takes about 1.6 GiB: budget at least 8 GiB of disk for the base plus three stages,
plus environment and headroom. Peak RAM/VRAM was not measured in the experiment.

Shared hyper-parameters: seed 771, batch size 4, AdamW,
weight decay 0.01, clip grad norm 1. The decision head trains `head`, `scorer`, `type_emb`. All other parameters
are frozen except the last three encoder layers in v3. Their learning
rate (LR) is fixed: 1e-5.
`act_head` is not trained. The encoder stays in eval mode, including while training
the last layers. The loss is cross-entropy over the chosen question option.
Temperature is reset to 1; no separate probability calibration is done.

The model is saved when the summed accuracy of `command + weapon` answers
on the validation split strictly increased. This metric scores question answers,
not game playthroughs.
Final weights correspond to the best epoch, not necessarily the last one.
If no epoch improved, the base weights remain without `best-epoch.json`;
the adaptation server rejects such a result.

Original v3: best epoch 5, accuracy command 72.5%, weapon 98%.
The same seed does not guarantee bit-identical weights across devices
and library versions. To repeat the final game run, use the released model
with the stated SHA-256.

## 3. Check the training in game

```bash
.venv/bin/python serve_doom_laya.py \
  --checkpoint checkpoints/laya-doom-v3-repro --device mps --port 8001
```

In another terminal:

```bash
.venv/bin/python agent.py --model doom-adapted --seed 48 \
  --seconds 180 --record auto --show --stop-after-level
.venv/bin/python -m tools.check_authority runs/<printed-run>
.venv/bin/python -m tools.verify_run runs/<printed-run>
```

The check requires an engine-confirmed MAP01 completion plus three seconds of MAP02.
The player must stay alive, telemetry must be consistent, and game speed must
match real time. If the model did not finish,
the check returns FAIL. Do not select the epoch on seed 48: for development use
a separate series of validation runs and keep the failed runs.

For further evaluation, run several new seeds with the same settings
and no retraining on them. Passing the current seed 48 does not promise passing all seeds.

## 4. Build your own training examples

`training/build_dataset.py` takes telemetry from `runs/<name>/telemetry.jsonl`.
First collect separate game runs for training and validation, then write
a `sources.json` file, for example:

```json
{
  "train": ["my-train-seed42", "my-train-seed43"],
  "validation": ["my-validation-seed44"]
}
```

```bash
.venv/bin/python training/build_dataset.py \
  --runs-dir runs --sources sources.json --output-dir training/custom
.venv/bin/python training/finetune.py \
  --data training/custom --encoder-last 3 --epochs 5 --lr 0.0001 \
  --output checkpoints/custom --device auto
```

The generator targets MAP01: for another map, pass its geometry
instead of the fixed MAP01 and revisit the labels. One source run must not
appear in both the training and validation splits. To repeat v3 training, use the frozen data,
not freshly collected game trajectories.

## 5. Prepare a checkpoint for distribution

```bash
.venv/bin/python scripts/package_model.py \
  --checkpoint checkpoints/laya-doom-v3 --output dist/laya-doom-v3 --archive
```

This produces a Hugging Face directory and a GitHub Releases archive with SHA-256.
This script does not publish anything. For your own model, update
`model-card/README.md`: the results and hash in the template refer to the original v3.
Details — [PUBLISHING.en.md](PUBLISHING.en.md).
