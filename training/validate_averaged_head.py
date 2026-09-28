"""Evaluate an averaged head and its exact parent before permitting API use."""
import os
os.environ['USE_TF']='0';os.environ['USE_TORCH']='1';os.environ['TOKENIZERS_PARALLELISM']='false'
import argparse,collections,hashlib,json
from pathlib import Path


def validate(checkpoint,base,data,device):
    import torch
    from laya import Agent
    from laya.common import build_sequence
    from doomlib.question_heads import load_head
    torch.set_num_threads(4)
    def digest(path):
        with path.open('rb') as h:return hashlib.file_digest(h,'sha256').hexdigest()
    cfg=json.loads((checkpoint/'rl_agent_config.json').read_text());average=cfg['doom_adaptation']['head_average']
    if average['base_sha256']!=digest(base/'model.safetensors'):raise ValueError('Different averaging parent')
    parent=Agent(str(base),device=device);candidate=load_head(parent,base,checkpoint)
    rows=json.loads(data.read_text());prepared=[]
    for row in rows:
        q=row['question'];ids,marks=build_sequence(parent.tok,row['state'],dict(t='choice',ins=q['instructions'],crit=q['criteria']),parent.cfg['max_len'],parent.cfg['head_max_len'])
        prepared.append((ids,marks,list(q['criteria']).index(row['label']),row.get('category','uncategorized')))
    correct=collections.Counter();categories={name:collections.defaultdict(lambda:dict(correct=0,total=0)) for name in ('base','average')}
    with torch.no_grad():
        for start in range(0,len(prepared),4):
            batch=prepared[start:start+4];length=max(len(r[0]) for r in batch);k=max(2,max(len(r[1]) for r in batch))
            ids=torch.full((len(batch),length),parent.tok.pad_token_id,dtype=torch.long,device=device);att=torch.zeros_like(ids);marks=torch.zeros((len(batch),k),dtype=torch.long,device=device);mask=torch.zeros((len(batch),k),dtype=torch.bool,device=device);types=torch.zeros(len(batch),dtype=torch.long,device=device)
            for i,(tokens,indices,_,_) in enumerate(batch):
                ids[i,:len(tokens)]=torch.tensor(tokens,device=device);att[i,:len(tokens)]=1;marks[i,:len(indices)]=torch.tensor(indices,device=device);mask[i,:len(indices)]=True
            encoded=parent.model.encoder(input_ids=ids,attention_mask=att).last_hidden_state
            for name,agent in (('base',parent),('average',candidate)):
                model=agent.model;h=encoded+model.type_emb(types)[:,None,:]
                for layer in model.head.layers:h=layer(h,src_key_padding_mask=~att.bool())
                selected=torch.gather(h,1,marks[:,:,None].expand(-1,-1,h.shape[-1]));logits=model.scorer(selected).squeeze(-1).float().masked_fill(~mask,-1e4)
                if start==0:
                    parity=float((logits-model(ids,att,marks,mask,types)[0]).abs().max())
                    if parity>1e-4:raise ValueError('Shared encoder forward differs')
                for guess,(_,_,label,category) in zip(logits.argmax(-1).cpu().tolist(),batch):
                    hit=guess==label;correct[name]+=hit;categories[name][category]['correct']+=hit;categories[name][category]['total']+=1
            if start%100==0:print('EVAL',start,len(prepared),flush=True)
    report=dict(epoch=None,method='post-training-head-weight-average',note='Legacy best-epoch filename is the API validation certificate. This checkpoint is an evaluated fixed weight average, not a newly trained epoch. Development validation only; gameplay is separate.',weights_sha256=digest(checkpoint/'model.safetensors'),parent_sha256=average['base_sha256'],validation_data=str(data),validation_data_sha256=digest(data),rows=len(rows),baseline_validation=dict(command=correct['base']/len(rows)),validation=dict(command=correct['average']/len(rows)),validation_categories=categories['average'],baseline_categories=categories['base'],head_average=average)
    (checkpoint/'average-validation.json').write_text(json.dumps(report,indent=2)+'\n')
    if correct['average']<=correct['base']:raise ValueError('Average did not improve validation')
    (checkpoint/'best-epoch.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if not k.endswith('categories')},indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--checkpoint',type=Path,required=True);p.add_argument('--base',type=Path,required=True);p.add_argument('--data',type=Path,required=True);p.add_argument('--device',default='mps');a=p.parse_args();validate(a.checkpoint,a.base,a.data,a.device)
