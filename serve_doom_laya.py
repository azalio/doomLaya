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
    parser.add_argument("--item-without-goal", action="store_true", help="Omit only the previous command line for the item head; preserves all physical facts and choices")
    parser.add_argument("--command-without-goal", action="store_true", help="Omit only the previous command line for the command head; preserves execution results, facts and choices")
    parser.add_argument("--enemy-without-goal", action="store_true", help="Omit only the previous command line for the enemy head; preserves enemy facts and all target choices")
    parser.add_argument("--enemy-compact-facts", action="store_true", help="Use the trained sequence head with compact health/inventory state; retain all target facts and orders")
    parser.add_argument("--enemy-rank-facts", action="store_true", help="Use a trained neural target ranker and expose probabilities of every original firing plan")
    parser.add_argument("--item-category-facts", action="store_true", help="Use a trained resource head with observed item categories and compact player facts")
    parser.add_argument("--item-compact-facts", action="store_true", help="Use a trained item head with observed health, armor, inventory, keys and reachability")
    parser.add_argument("--weapon-compact-facts", action="store_true", help="Use a trained weapon head with observed health, inventory and enemy state")
    parser.add_argument("--movement-compact-facts", action="store_true", help="Use the trained compact observed-geometry input for movement")
    parser.add_argument("--model", choices=["typed-decisions", "doom-adapted"], default="doom-adapted")
    parser.add_argument("--device", choices=["auto", "cpu", "mps", "cuda"], default="auto")
    parser.add_argument("--port", type=int)
    parser.add_argument("--precision", choices=["native", "encoder-bfloat16"], default="native", help="Native precision, or bfloat16 encoder with float32 decision heads (MPS only)")
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
    if args.item_without_goal and "item" not in head_specs:
        parser.error("--item-without-goal requires an explicit item head")
    if args.command_without_goal and "command" not in head_specs:
        parser.error("--command-without-goal requires an explicit command head")
    if args.enemy_without_goal and "enemy" not in head_specs:
        parser.error("--enemy-without-goal requires an explicit enemy head")
    if args.movement_compact_facts and "movement" not in head_specs:
        parser.error("--movement-compact-facts requires an explicit movement head")
    if args.enemy_compact_facts and "enemy" not in head_specs:
        parser.error("--enemy-compact-facts requires an explicit enemy head")
    if args.enemy_rank_facts and "enemy" not in head_specs:
        parser.error("--enemy-rank-facts requires an explicit enemy head")
    if args.enemy_rank_facts and args.enemy_compact_facts:
        parser.error("Choose one enemy input projection")
    if args.weapon_compact_facts and "weapon" not in head_specs:
        parser.error("--weapon-compact-facts requires an explicit weapon head")
    if args.item_category_facts and args.item_compact_facts:
        parser.error("Choose one item input projection")
    if (args.item_compact_facts or args.item_category_facts) and "item" not in head_specs:
        parser.error("--item-compact-facts requires an explicit item head")
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
    if args.precision != "native" and device != "mps":parser.error("encoder-bfloat16 is currently tested only on MPS")
    precision = "encoder_bfloat16_head_float32" if args.precision != "native" else str(model.dtype).removeprefix("torch.")
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
        for question in ("enemy","movement"):
            if question in overrides:
                question_format=overrides[question].cfg.get("doom_adaptation",{}).get("question_format")
                if question_format:head_metadata[question]["question_format"]=question_format
        if 'movement' in overrides and head_metadata['movement'].get('question_format')=='movement-compact-v1' and not args.movement_compact_facts:
            raise ValueError('Compact movement head requires --movement-compact-facts')
        if 'enemy' in overrides and overrides['enemy'].cfg.get('doom_adaptation',{}).get('input_projection')=='enemy-compact-v1' and not args.enemy_compact_facts:
            raise ValueError('Compact enemy head requires --enemy-compact-facts')
        if 'enemy' in overrides and overrides['enemy'].cfg.get('doom_adaptation',{}).get('input_projection')=='enemy-ranking-v1' and not args.enemy_rank_facts:
            raise ValueError('Ranked enemy head requires --enemy-rank-facts')
        if args.enemy_rank_facts:
            from doomlib.enemy_ranking import FORMAT
            if overrides['enemy'].cfg.get('doom_adaptation',{}).get('input_projection')!=FORMAT:raise ValueError('Enemy head was not trained for target ranking')
            head_metadata['enemy'].update(input_projection=FORMAT,state_projection=FORMAT,composition='plackett-luce-nonempty-v1')
        if args.movement_compact_facts:
            from doomlib.compact_movement import FORMAT
            if head_metadata["movement"].get("question_format")!=FORMAT:raise ValueError("Movement head was not trained on compact inputs")
            head_metadata["movement"]["input_projection"]=FORMAT
        if args.enemy_compact_facts:
            from doomlib.compact_enemy import FORMAT
            if overrides['enemy'].cfg.get('doom_adaptation',{}).get('input_projection')!=FORMAT:raise ValueError('Enemy head was not trained on compact inputs')
            head_metadata['enemy']['input_projection']=FORMAT
        if 'weapon' in overrides and overrides['weapon'].cfg.get('doom_adaptation',{}).get('input_projection')=='weapon-compact-v1' and not args.weapon_compact_facts:
            raise ValueError('Compact weapon head requires --weapon-compact-facts')
        if args.weapon_compact_facts:
            from doomlib.compact_weapon import FORMAT
            if overrides['weapon'].cfg.get('doom_adaptation',{}).get('input_projection')!=FORMAT:raise ValueError('Weapon head was not trained on compact inputs')
            head_metadata['weapon'].update(input_projection=FORMAT,state_projection=FORMAT)
        if 'item' in overrides and overrides['item'].cfg.get('doom_adaptation',{}).get('input_projection')=='item-compact-v1' and not args.item_compact_facts:
            raise ValueError('Compact item head requires --item-compact-facts')
        if 'item' in overrides and overrides['item'].cfg.get('doom_adaptation',{}).get('input_projection')=='item-category-v2' and not args.item_category_facts:
            raise ValueError('Category item head requires --item-category-facts')
        if args.item_compact_facts or args.item_category_facts:
            from doomlib.compact_item import FORMAT,CATEGORY_FORMAT
            expected=CATEGORY_FORMAT if args.item_category_facts else FORMAT
            if overrides['item'].cfg.get('doom_adaptation',{}).get('input_projection')!=expected:raise ValueError('Item head was not trained on the selected input format')
            head_metadata['item'].update(input_projection=expected,state_projection=expected)
        head_metadata["shared_encoder_verified"] = True
        if args.precision != "native":
            for info in head_metadata.values():
                if isinstance(info,dict):info["inference_precision"] = precision
        if "look_gate" in head_specs:
            head_metadata["look_gate"].update(composition="probability-mixture-v1",input_projection="observed-look-facts-v2-optional-floor")
        if args.item_without_goal and not (args.item_compact_facts or args.item_category_facts):
            head_metadata["item"]["state_projection"] = "without-current-command-v1"
        if args.command_without_goal:
            head_metadata["command"]["state_projection"] = "without-current-command-v1"
        if args.enemy_compact_facts:
            head_metadata["enemy"]["state_projection"] = "enemy-compact-v1"
        elif args.enemy_without_goal and not args.enemy_rank_facts:
            head_metadata["enemy"]["state_projection"] = "without-current-command-v1"
        inference = QuestionHeads(model, overrides, item_without_goal=args.item_without_goal, command_without_goal=args.command_without_goal, enemy_without_goal=args.enemy_without_goal, movement_compact_facts=args.movement_compact_facts, enemy_compact_facts=args.enemy_compact_facts, enemy_rank_facts=args.enemy_rank_facts, weapon_compact_facts=args.weapon_compact_facts, item_compact_facts=args.item_compact_facts, item_category_facts=args.item_category_facts)
        warmup_questions={question: {"type": "choice", "instructions": "Choose the available option.", "criteria": {"ready": "Ready"}} for question in overrides}
        warmup_state="Inference warmup"
        if args.movement_compact_facts:
            from doomlib.decision_questions import MOVEMENTS
            from doomlib.movement_questions import describe_movement
            warmup_state="Enemies: Zombieman#1 8.0m (visible).\nMovement: stationary."
            warmup_questions['movement']=describe_movement(dict(type='choice',instructions='Choose movement.',criteria=MOVEMENTS),dict(left=6,right=6,back=6))
        if args.enemy_compact_facts or args.enemy_rank_facts:
            from doomlib.enemy_sequences import with_enemy_sequences
            warmup_state += "\nHP 100; armor 0.\nInventory: pistol 50 ammo."
            packet=with_enemy_sequences(dict(state=warmup_state,questions={'enemy':{}},targets={'enemy':{'1':dict(id=1,name='Zombieman',distance=8,bearing=0,visible=True)}}))
            warmup_questions['enemy']=packet['questions']['enemy']
        if args.weapon_compact_facts:
            if '\nHP ' not in warmup_state:warmup_state+='\nHP 100; armor 0.\nInventory: pistol 50 ammo.'
            warmup_questions['weapon']=dict(type='choice',instructions='Choose weapon',criteria={'pistol':'Basic ranged gun. Loaded: yes. Ammo: 50.','keep':'Keep the current weapon.'})
        if (args.item_compact_facts or args.item_category_facts) and not any(line.startswith("HP ") for line in warmup_state.splitlines()):
            warmup_state+="\nHP 100; armor 0.\nInventory: pistol 50 ammo."
        if args.item_category_facts:
            warmup_state+='\nItems: Stimpack#1 [Health] 2.0m.'
            warmup_questions['item']=dict(type='choice',instructions='Choose item',criteria={'1':'Stimpack; reachable; 2.0m.'})
        inference.predict(warmup_state,warmup_questions)
        print("QUESTION_HEADS", json.dumps(head_metadata), flush=True)
    if args.precision == "encoder-bfloat16":
        model.model.encoder.to(dtype=torch.bfloat16)
        names = list(overrides) if head_specs else ["ready"]
        if head_specs:inference.predict(warmup_state,warmup_questions)
        else:inference.predict("Precision warmup", {name: {"type": "choice", "instructions": "Choose the available option.", "criteria": {"ready": "Ready"}} for name in names})
        print("PRECISION_WARMUP", precision, flush=True)
    lock = threading.Lock()
    app = FastAPI()
    with (root / "model.safetensors").open("rb") as handle:
        weights_hash = hashlib.file_digest(handle, "sha256").hexdigest()
    metadata = {"status": "ok", "inference_precision": precision, "models": {args.model: device},
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
        result["routing"] = {"model": args.model, "inference_precision": precision, "checkpoint": root.name,
                             "weights_sha256": weights_hash, "decoding": decoder.metadata(), "compatibility": ["single-option-padding"]}
        if head_metadata is not None:
            result["routing"].update(weights_sha256_kind="question_heads_manifest", question_heads=head_metadata)
        result["latency_ms"] = round((time.perf_counter() - started) * 1000, 2)
        return result

    port = args.port if args.port is not None else (8001 if args.model == "doom-adapted" else 8000)
    uvicorn.run(app, host="127.0.0.1", port=port)


if __name__ == "__main__":
    main()
