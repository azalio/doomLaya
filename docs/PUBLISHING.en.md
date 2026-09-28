# Publishing code, weights and video

## v0.3.1: MAP01–MAP03

[Weights and training dependencies](https://huggingface.co/azalio/laya-doom-map03/tree/v0.3.1) ·
[Three videos and telemetry](https://github.com/azalio/doomLaya/releases/tag/v0.3.1) ·
[Run and train (Russian)](REGRESSION-FIX.md).

Source and datasets are in the GitHub `v0.3.1` tag. The optional HF
`training-assets/` directory contains six parent models, four semantic caches
and two retention traces. Inference does not need it. The packaging commands
are in the [Russian guide](PUBLISHING.md#v031-map01map03).
Older weights remain available at HF tag `v0.3.0`.

The sections below describe previous releases.

The v0.2.0 five-head model is published separately at
[azalio/laya-doom-map02](https://huggingface.co/azalio/laya-doom-map02).
Use [MAP02.md (Russian)](MAP02.md) for its download and launch commands.
The v3 packaging commands below describe the older v0.1.0 release.

[English](PUBLISHING.en.md) · [Русский](PUBLISHING.md) — this file is the English version.

Recommended layout: **GitHub — code, training data and report;
Hugging Face — model; GitHub Releases — video and optionally the weights archive.**
Preparation scripts create local files. Uploading to the services is described separately
in steps 3 and 4.

Project addresses: [code](https://github.com/azalio/doomLaya), [model](https://huggingface.co/azalio/laya-doom-v3),
[release v0.1.0](https://github.com/azalio/doomLaya/releases/tag/v0.1.0). To download the ready weights, jump to step 5.

## Where to store weights

The current `model.safetensors` is about 1.6 GiB, the full directory roughly the same
size. GitHub blocks files larger than 100 MiB on upload via plain Git.
[GitHub limits](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github).

| Option | Fits | Notes |
|---|---|---|
| Hugging Face model repository | Recommended | Model card, revisions, `hf download` |
| GitHub Release asset | Yes | Archive downloads separately, source Git stays small |
| GitHub LFS | Yes | Needs LFS client; storage and downloads depend on plan quotas |
| Plain Git commit | No | Weights exceed 100 MiB |

At check time GitHub ties the per-file release limit to the LFS limit
of the chosen plan: Free/Pro — 2 GB. The current archive fits.
[Release assets](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-large-files-on-github#distributing-large-binaries),
[LFS](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-git-large-file-storage).
Hugging Face offers public storage on a best-effort basis,
with no guaranteed quota for a free account;
[current storage rules](https://huggingface.co/docs/hub/storage-limits).

## 1. Check the sources

```bash
.venv/bin/python -m unittest tests.test_authority tests.test_publication
.venv/bin/python scripts/check_publication.py
git diff --cached --stat
```

The script checks files that will land in Git: it looks for secrets, personal absolute paths,
links to missing local documents and large files. It prints only
the names of problem files, never secret values.

Git holds code, CI, docs, frozen training JSON, fixtures,
the model card and small verification reports. `.env`, environments, `runs/`,
`checkpoints/`, `dist/`, WADs, videos, old drafts and original third-party
materials are excluded. Local files stay on disk.

## 2. Prepare the model

```bash
.venv/bin/python scripts/package_model.py --archive
(cd dist/laya-doom-v3 && shasum -a 256 -c SHA256SUMS)
(cd dist && shasum -a 256 -c laya-doom-v3.tar.sha256)
```

The script copies only the needed files, adds the model card, Apache-2.0 and NOTICE,
strips local paths from metadata and creates `SHA256SUMS`.
The source model is unchanged. The output folder must not exist;
for a rebuild use a different `--output` value.

You get `dist/laya-doom-v3/`, `dist/laya-doom-v3.tar` and the archive checksum.
Weights are identical in both variants:
`bb9083189517c5dc5c0e357062446df2ea73eadc3d909ec6ec7a6cee222a6147`.

## 3. Publish code and model

The commands below publish files to GitHub and Hugging Face. Replace account names
with your own. Repository-creation commands are only needed for a new publication;
for an existing repository just upload the changes.

GitHub via installed `gh`:

```bash
git add .
git commit -m "Prepare reproducible Doom model comparison"
gh repo create azalio/doomLaya --public --source=. --remote=origin --push
```

If the repository already exists, add its address as a remote instead of `gh repo create`
and run a normal `git push -u origin main`.

Hugging Face via the CLI from `requirements-model.txt`:

```bash
.venv/bin/hf auth login
HF_MODEL=azalio/laya-doom-v3
.venv/bin/hf repo create "$HF_MODEL" --repo-type model
.venv/bin/hf upload "$HF_MODEL" dist/laya-doom-v3 .
```

Enter the HF key interactively or pass it via `HF_TOKEN`;
it must not be in the sources. After upload, add the model URL to the README
plus the commit hash that pins its version.
This project's code and model live under the `azalio` account.

## 4. Add video and archive to a GitHub Release

```bash
gh release create v0.1.0 \
  --title "Doom model-owned decisions: Laya v3 and Jev" \
  --notes-file RELEASE_NOTES.md \
  dist/laya-doom-v3.tar dist/laya-doom-v3.tar.sha256 \
  runs/20260922_000150_decision-model-comparison/laya-vs-jev.mp4 \
  runs/20260922_000150_decision-model-comparison/original-laya-vs-jev.mp4
```

If weights live only on Hugging Face, drop the two `dist/` arguments.
Videos exist in the author's original working folder; a fresh clone has none.
Cross-check SHA-256 via [reports/video-verification.json](../reports/video-verification.json).
After publishing, add release-file links to README and COMPARISON.

## 5. Download the published weights on another machine

To download v3 from Hugging Face, run from the doomLaya root;
it pins the published-version hash:

```bash
HF_MODEL=azalio/laya-doom-v3
HF_REVISION=d27276e3bf8275cdbc9a7a72d80cad656aa87bd7
.venv/bin/hf download "$HF_MODEL" --revision "$HF_REVISION" \
  --local-dir checkpoints/laya-doom-v3
(cd checkpoints/laya-doom-v3 && shasum -a 256 -c SHA256SUMS)
```

Or via GitHub Release:

```bash
mkdir -p dist checkpoints
gh release download v0.1.0 --repo azalio/doomLaya \
  --pattern 'laya-doom-v3.tar*' --dir dist
(cd dist && shasum -a 256 -c laya-doom-v3.tar.sha256)
tar -xf dist/laya-doom-v3.tar -C checkpoints
```

Then start the server per [README](../README.en.md). To train your own model,
see [TRAINING.en.md](TRAINING.en.md).
