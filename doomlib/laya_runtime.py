"""Pinned upstream checkpoint and explicit CPU/MPS/CUDA selection."""
from pathlib import Path

BASE_REPO = "convaiinnovations/laya"
BASE_REVISION = "1c5edc17a7acd8701df6fc341c0d179f1c62c982"
LAYA_SOURCE_COMMIT = "42626c348753fbb17572a813127df2278a1ec527"


def choose_device(requested="auto"):
    import torch
    if requested == "auto":
        if torch.cuda.is_available():
            return "cuda"
        return "mps" if torch.backends.mps.is_available() else "cpu"
    if requested == "mps" and not torch.backends.mps.is_available():
        raise RuntimeError("MPS is unavailable; use --device cpu or cuda")
    if requested == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA is unavailable; use --device cpu or mps")
    return requested


def base_checkpoint(local=None):
    if local:
        path = Path(local).expanduser().resolve()
    else:
        from huggingface_hub import snapshot_download
        path = Path(snapshot_download(
            BASE_REPO, revision=BASE_REVISION,
            allow_patterns=["typed-decisions/*"],
        )) / "typed-decisions"
    if not (path / "model.safetensors").is_file():
        raise FileNotFoundError(f"Not a Laya checkpoint: {path}")
    return path


def enable_single_option_padding(model):
    """Pad the masked option axis for upstream's topk(2) confidence features."""
    def pad_options(module,args):
        import torch
        ids,attention,markers,mask,qtype,*rest=args
        if markers.shape[1]!=1:return args
        markers=torch.cat((markers,torch.zeros_like(markers)),dim=1)
        mask=torch.cat((mask,torch.zeros_like(mask)),dim=1)
        return (ids,attention,markers,mask,qtype,*rest)
    return model.register_forward_pre_hook(pad_options)
