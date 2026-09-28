"""Average compatible trained decision heads; retain and verify the frozen encoder."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil


def average(base,adapted,alpha,output):
    if not 0<alpha<1:raise ValueError('alpha must be between zero and one')
    if output.exists():raise ValueError('Output exists')
    import torch
    from safetensors import safe_open
    from safetensors.torch import save_file
    configs=[json.loads((path/'rl_agent_config.json').read_text()) for path in (base,adapted)]
    for key in ('encoder','head_layers','max_len','head_max_len'):
        if configs[0].get(key)!=configs[1].get(key):raise ValueError('Incompatible '+key)
    if configs[0].get('doom_adaptation',{}).get('input_projection')!=configs[1].get('doom_adaptation',{}).get('input_projection'):raise ValueError('Different input projections')
    for source in (base/'tokenizer').rglob('*'):
        if source.is_file() and source.read_bytes()!=(adapted/'tokenizer'/source.relative_to(base/'tokenizer')).read_bytes():raise ValueError('Different tokenizers')
    values={}
    with safe_open(str(base/'model.safetensors'),framework='pt',device='cpu') as first,safe_open(str(adapted/'model.safetensors'),framework='pt',device='cpu') as second:
        if set(first.keys())!=set(second.keys()):raise ValueError('Different tensor keys')
        for key in first.keys():
            a,b=first.get_tensor(key),second.get_tensor(key)
            if a.shape!=b.shape or a.dtype!=b.dtype:raise ValueError('Different tensor layout: '+key)
            if key.startswith('encoder.'):
                if not torch.equal(a,b):raise ValueError('Encoder changed: '+key)
                values[key]=a
            elif key.startswith(('head.','scorer.','type_emb.')):
                values[key]=((1-alpha)*a.float()+alpha*b.float()).to(a.dtype).contiguous()
            else:
                if not torch.equal(a,b):raise ValueError('Unexpected changed tensor: '+key)
                values[key]=a
        output.mkdir()
        for name in ('encoder','tokenizer'):shutil.copytree(base/name,output/name)
        def digest(path):
            with path.open('rb') as handle:return hashlib.file_digest(handle,'sha256').hexdigest()
        config=configs[1]
        config['doom_adaptation']['head_average']=dict(alpha_adapted=alpha,base=base.name,adapted=adapted.name,base_sha256=digest(base/'model.safetensors'),adapted_sha256=digest(adapted/'model.safetensors'),note='Fixed learned weight average, selected on development regression cases; gameplay validation is separate. No runtime policy.')
        (output/'rl_agent_config.json').write_text(json.dumps(config,indent=2)+'\n')
        shutil.copy2(__file__,output/'average_script.py')
        save_file(values,str(output/'model.safetensors'))
    print(json.dumps(dict(checkpoint=str(output),sha256=digest(output/'model.safetensors'),head_average=config['doom_adaptation']['head_average']),indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--base',type=Path,required=True);p.add_argument('--adapted',type=Path,required=True);p.add_argument('--alpha',type=float,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();average(a.base,a.adapted,a.alpha,a.output)
