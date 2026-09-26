"""Serve the pinned original Laya or a separate Doom-adapted checkpoint."""
import os
os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("USE_TORCH", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
import argparse
import hashlib
import json
import threading
import time
from pathlib import Path
from doomlib.laya_runtime import BASE_REPO, BASE_REVISION, LAYA_SOURCE_COMMIT, base_checkpoint, choose_device, enable_single_option_padding

from doomlib import ensure_utf8_stdio

ensure_utf8_stdio()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", help="Local adapted checkpoint directory")
    parser.add_argument("--item-head-checkpoint", help="Use a separately trained item head with the identical frozen encoder")
    parser.add_argument("--head-checkpoint", action="append", default=[], metavar="QUESTION=PATH", help="Use a fixed question-specific head; repeat for multiple questions")
    parser.add_argument("--model", choices=["typed-decisions", "doom-adapted"], default="doom-adapted")
    parser.add_argument("--device", choices=["auto", "cpu", "mps", "cuda"], default="auto")
    parser.add_argument("--port", type=int)
    parser.add_argument("--choice-temperature",type=float,default=0.,help="0 keeps argmax; positive values sample model probabilities")
    parser.add_argument("--sampling-seed",type=int,default=0)
    parser.add_argument("--sample-questions",nargs="+",help="Sample only these question names; other answers keep argmax")
    args = parser.parse_args()
    from doomlib.model_decoding import ChoiceDecoder
    decoder=ChoiceDecoder(args.choice_temperature,args.sampling_seed,args.sample_questions)
    if args.model == "doom-adapted" and not args.checkpoint:
        parser.error("--checkpoint is required for doom-adapted")
    if args.model == "typed-decisions" and args.checkpoint:
        parser.error("--checkpoint is reserved for doom-adapted; original weights use the pinned revision")
    from doomlib.question_heads import parse_head_specs
    try: head_specs = parse_head_specs(args.head_checkpoint, args.item_head_checkpoint)
    except ValueError as error: parser.error(str(error))
    if head_specs and args.model != "doom-adapted":
        parser.error("Question-specific heads require doom-adapted")
    import torch
    import uvicorn
    from fastapi import FastAPI, HTTPException
    from pydantic import BaseModel
    from laya import Agent

    torch.set_num_threads(4)
    device = choose_device(args.device)
    root = base_checkpoint(args.checkpoint)
    if args.model == "doom-adapted" and not (root / "best-epoch.json").exists():
        raise RuntimeError("No epoch improved held-out validation")
    model = Agent(str(root), device=device)
    enable_single_option_padding(model.model)
    warmup=model.predict("Inference warmup",{"ready":{"type":"choice","instructions":"Choose the available option.","criteria":{"ready":"Ready"}}})
    if warmup['answers']['ready']['choice']!='ready':raise RuntimeError('Single-option inference check failed')
    print('SINGLE_OPTION_WARMUP passed',flush=True)
    inference = model
    head_metadata = None
    if head_specs:
        from doomlib.question_heads import QuestionHeads, load_head
        def digest(path):
            with path.open("rb") as handle:
                return hashlib.file_digest(handle, "sha256").hexdigest()
        head_metadata = {"default": {"checkpoint": root.name, "weights_sha256": digest(root / "model.safetensors")}}
        loaded = {}; overrides = {}
        for question, path in sorted(head_specs.items()):
            head_root = base_checkpoint(path).resolve()
            if not (head_root / "best-epoch.json").exists():
                raise RuntimeError("Question head has no improved validation epoch: " + question)
            if head_root not in loaded:
                loaded[head_root] = load_head(model, root, head_root)
            overrides[question] = loaded[head_root]
            head_metadata[question] = {"checkpoint": head_root.name, "weights_sha256": digest(head_root / "model.safetensors")}
        head_metadata["shared_encoder_verified"] = True
        inference = QuestionHeads(model, overrides)
        inference.predict("Inference warmup", {question: {"type": "choice", "instructions": "Choose the available option.", "criteria": {"ready": "Ready"}} for question in overrides})
        print("QUESTION_HEADS", json.dumps(head_metadata), flush=True)
    lock = threading.Lock()
    app = FastAPI()
    with (root / "model.safetensors").open("rb") as handle:
        weights_hash = hashlib.file_digest(handle, "sha256").hexdigest()
    metadata = {"status": "ok", "models": {args.model: device},
                "checkpoint": root.name, "weights_sha256": weights_hash,
                "laya_source_commit": LAYA_SOURCE_COMMIT, "decoding": decoder.metadata(), "compatibility": ["single-option-padding"]}
    if head_metadata is not None:
        weights_hash = hashlib.sha256(json.dumps(head_metadata, sort_keys=True).encode()).hexdigest()
        metadata.update(weights_sha256=weights_hash, weights_sha256_kind="question_heads_manifest", question_heads=head_metadata)
    if args.model == "typed-decisions":
        metadata.update(repo=BASE_REPO, revision=BASE_REVISION)
    elif (root / "training-metrics.json").exists():
        metadata["training"] = json.loads((root / "training-metrics.json").read_text())

    class Request(BaseModel):
        state: str
        questions: dict
        model: str = args.model

    @app.get("/health")
    def health():
        return metadata

    @app.post("/predict")
    def predict(request: Request):
        if request.model != args.model:
            raise HTTPException(400, "Requested model is not loaded by this server")
        started = time.perf_counter()
        with lock:
            result = decoder.apply(inference.predict(request.state, request.questions))
        result["routing"] = {"model": args.model, "checkpoint": root.name,
                             "weights_sha256": weights_hash, "decoding": decoder.metadata(), "compatibility": ["single-option-padding"]}
        if head_metadata is not None:
            result["routing"].update(weights_sha256_kind="question_heads_manifest", question_heads=head_metadata)
        result["latency_ms"] = round((time.perf_counter() - started) * 1000, 2)
        return result

    port = args.port if args.port is not None else (8001 if args.model == "doom-adapted" else 8000)
    uvicorn.run(app, host="127.0.0.1", port=port)


if __name__ == "__main__":
    main()
