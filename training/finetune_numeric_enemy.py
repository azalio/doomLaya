"""Fit a learned geometric ranking residual over frozen Laya target scores."""
import argparse
import copy
import hashlib
import json
import math
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import time
os.environ.update(USE_TF='0', USE_TORCH='1', TOKENIZERS_PARALLELISM='false')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from doomlib.numeric_enemy import FORMAT, PROJECTION, FEATURES, NAMES, observations, make_model
from doomlib.enemy_ranking import STOP, ranking_input, sequence_probabilities
from doomlib.enemy_sequences import with_enemy_sequences
from training.build_map3_enemy_sequences import order_for


def digest(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def synthetic(count,seed):
    rng=random.Random(seed)
    for _ in range(count):
        enemies={str(i):dict(id=i,name=rng.choice(NAMES),distance=rng.randint(1,192)/4,
                             bearing=rng.randint(-180,180),visible=rng.random()<.7) for i in range(rng.randint(1,3))}
        packet=dict(state='HP 80; armor 0.\nInventory: pistol 50 ammo; shotgun 12 ammo.',
                    questions={'enemy':{}},targets={'enemy':enemies},
                    enemy_commitment={'target_id':rng.choice([None]+list(enemies))})
        packet=with_enemy_sequences(packet);order=order_for(packet)
        state,question,orders=ranking_input(packet['state'],packet['questions']['enemy'])
        yield dict(state=state,question=question,label=order[0],target_ranking=order+[STOP],enemy_sequences=orders,
                   sequence_label=next(k for k,v in orders.items() if v==order))


def ranking_loss(scores,mask,order,stop):
    import torch
    remaining=mask.clone();loss=torch.zeros(len(scores),device=scores.device)
    for step in range(order.shape[1]):
        selected=order[:,step];active=selected>=0
        available=remaining.clone()
        if step==0:available.scatter_(1,stop[:,None],False)
        # Ended rows contribute no loss; keep a finite normalization for them.
        available[~active,0]=True
        index=selected.clamp_min(0)
        ce=torch.logsumexp(scores.masked_fill(~available,-1e4),-1)-scores.gather(1,index[:,None]).squeeze(1)
        loss+=(3 if step==0 else 1)*ce*active
        remaining.scatter_(1,index[:,None],False)
    return loss.mean()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('base','data','cache','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--epochs',type=int,default=250)
    p.add_argument('--augmentation',type=int,default=16000)
    a=p.parse_args()
    if a.output.exists():p.error('Output exists')
    import torch
    from safetensors.torch import save_file
    torch.set_num_threads(2);torch.manual_seed(771)
    rows={s:json.loads((a.data/(s+'.json')).read_text()) for s in ('train','validation')}
    cache=json.loads(a.cache.read_text())
    identity=dict(semantic_weights=digest(a.base/'model.safetensors'),data={s:digest(a.data/(s+'.json')) for s in rows})
    if cache['identity']!=identity:raise ValueError('Semantic cache differs')
    priors={s:[[math.log(max(answer['probabilities'][k],1e-30)) for k in row['question']['criteria']]
               for row,answer in zip(rows[s],cache['answers'][s],strict=True)] for s in rows}
    for split,count,seed in [('synthetic_train',a.augmentation,272901),('synthetic_validation',3000,272902)]:
        rows[split]=list(synthetic(count,seed));priors[split]=[]
        for row in rows[split]:
            priors[split].append(torch.log_softmax(torch.randn(len(row['question']['criteria']))*4,-1).tolist())
    prepared={};training_features=[]
    for split,group in rows.items():
        x=torch.zeros(len(group),4,len(FEATURES));b=torch.zeros(len(group),4)
        mask=torch.zeros(len(group),4,dtype=torch.bool);order=torch.full((len(group),4),-1,dtype=torch.long)
        stop=torch.zeros(len(group),dtype=torch.long)
        for index,row in enumerate(group):
            keys=list(row['question']['criteria']);values=observations(row['state'],row['question']);n=len(keys)
            x[index,:n]=torch.tensor(values);b[index,:n]=torch.tensor(priors[split][index]);mask[index,:n]=True
            order[index,:len(row['target_ranking'])]=torch.tensor([keys.index(k) for k in row['target_ranking']]);stop[index]=keys.index(STOP)
            if split in ('train','synthetic_train'):training_features.extend(values)
        prepared[split]=(x,b,mask,order,stop)
    values=torch.tensor(training_features);thresholds={}
    for index in range(len(FEATURES)):
        unique=values[:,index].unique().sort().values
        if len(unique)>3:thresholds[str(index)]=torch.quantile(unique,torch.linspace(0,1,min(65,len(unique)))).tolist()
    spec=dict(format=FORMAT,input_projection=PROJECTION,features=list(FEATURES),thresholds=thresholds,hidden_size=96,probability_floor=1e-30)
    model=make_model(spec);optimizer=torch.optim.AdamW(model.parameters(),lr=.002,weight_decay=.0001)
    train=tuple(torch.cat([real.repeat((6,)+(1,)*(real.ndim-1)),extra]) for real,extra in zip(prepared['train'],prepared['synthetic_train']))
    def evaluate(split):
        x,b,mask,order,stop=prepared[split]
        with torch.no_grad():
            scores=model(x,b).masked_fill(~mask,-1e4);eligible=mask.clone().scatter_(1,stop[:,None],False)
            correct=scores.masked_fill(~eligible,-1e4).argmax(-1)==order[:,0]
            return int(correct.sum()),len(correct)
    initial=evaluate('validation');best=None;best_state=None;history=[];start=time.monotonic()
    for epoch in range(a.epochs):
        for indices in torch.randperm(len(train[0])).split(256):
            x,b,mask,order,stop=(value[indices] for value in train)
            loss=ranking_loss(model(x,b),mask,order,stop)
            optimizer.zero_grad();loss.backward();optimizer.step()
        val=evaluate('validation');syn=evaluate('synthetic_validation');score=.8*val[0]/val[1]+.2*syn[0]/syn[1]
        history.append(dict(epoch=epoch+1,validation=val,synthetic=syn,score=score))
        if best is None or score>best:best=score;best_epoch=epoch+1;best_state=copy.deepcopy(model.state_dict())
        if (epoch+1)%25==0:print(json.dumps(history[-1]),flush=True)
    model.load_state_dict(best_state)
    final={s:evaluate(s) for s in ('train','validation','synthetic_validation')}
    if final['validation'][0]<=initial[0]:raise ValueError('No improvement on recorded validation')
    def clone(source,target):
        if sys.platform=='darwin':subprocess.run(['/bin/cp','-c',str(source),str(target)],check=True)
        else:shutil.copyfile(source,target)
        return target
    shutil.copytree(a.base,a.output,copy_function=clone)
    (a.output/'numeric-residual.json').write_text(json.dumps(spec,indent=2)+'\n')
    save_file(best_state,str(a.output/'numeric-residual.safetensors'))
    cfg=json.loads((a.output/'rl_agent_config.json').read_text())
    cfg['doom_adaptation']['numeric_residual']=dict(format=FORMAT,spec_sha256=digest(a.output/'numeric-residual.json'),
        weights_sha256=digest(a.output/'numeric-residual.safetensors'),semantic_parent=a.base.name,identity=identity,
        seed=771,epochs=a.epochs,augmentation=a.augmentation,best_epoch=best_epoch,
        trainer_sha256=digest(__file__),inference_sha256=digest('doomlib/numeric_enemy.py'),
        labeler_sha256=digest('training/build_map3_enemy_sequences.py'),
        note='Frozen Laya ranker plus learned geometric scores; offline teacher labels and noisy synthetic semantic priors. No runtime labeler or option masking.')
    (a.output/'rl_agent_config.json').write_text(json.dumps(cfg,indent=2)+'\n')
    (a.output/'training-metrics.json').write_text(json.dumps(dict(initial=initial,final=final,best_epoch=best_epoch,seconds=time.monotonic()-start,history=history),indent=2)+'\n')
    (a.output/'best-epoch.json').write_text(json.dumps(dict(epoch=best_epoch,numeric_residual=True),indent=2)+'\n')
    destination=a.output/'source'/'training'/Path(__file__).name;destination.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(__file__,destination)
    print('CHECKPOINT',a.output,json.dumps(final),flush=True)


if __name__=='__main__':main()
