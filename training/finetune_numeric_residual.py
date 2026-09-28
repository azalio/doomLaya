"""Train an observed-number neural residual on frozen Laya semantic command scores."""
import argparse
import collections
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
os.environ.update(USE_TF='0', USE_TORCH='1', TOKENIZERS_PARALLELISM='false')
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from doomlib.numeric_command import ACTIONS, FORMAT, FUSION_FORMAT, FEATURE_FORMAT, STABLE_FORMAT, features, feature_names, item_distances, semantic_logits, make_residual_model


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--base', type=Path, required=True)
    p.add_argument('--data', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--cache', type=Path, required=True)
    p.add_argument('--epochs', type=int, default=350)
    p.add_argument('--device', default='mps')
    p.add_argument('--augmentation', type=int, default=0, help='Seeded synthetic physical observations; zero preserves the v1 architecture')
    p.add_argument('--survival-labels', action='store_true')
    p.add_argument('--resupply-labels', action='store_true')
    p.add_argument('--close-health-labels', action='store_true')
    p.add_argument('--visible-fight-labels', action='store_true')
    p.add_argument('--finish-route-labels', action='store_true')
    p.add_argument('--wide-inventory', action='store_true')
    p.add_argument('--wide-mechanisms', action='store_true')
    p.add_argument('--exit-loss-weight', type=float, default=1.0)
    a=p.parse_args()
    if not 0<a.exit_loss_weight<100:raise ValueError('Invalid exit loss weight')
    if a.output.exists(): raise ValueError('Output exists')
    import numpy as np
    import torch
    from safetensors.torch import save_file
    from laya import Agent
    from laya.common import build_sequence, collate_items, temp_bucket
    from doomlib.laya_runtime import enable_single_option_padding
    torch.set_num_threads(2);torch.manual_seed(771)
    rows={split:json.loads((a.data/(split+'.json')).read_text()) for split in ('train','validation')}
    identity=dict(semantic_weights=digest(a.base/'model.safetensors'), config=digest(a.base/'rl_agent_config.json'),
                  data={s:digest(a.data/(s+'.json')) for s in rows})
    if a.cache.exists():
        cache=json.loads(a.cache.read_text())
        if cache['identity']!=identity: raise ValueError('Cache identity differs')
    else:
        agent=Agent(str(a.base),device=a.device)
        enable_single_option_padding(agent.model)
        cache=dict(identity=identity, answers={})
        for split,group in rows.items():
            cached=[]
            for offset in range(0,len(group),4):
                chunk=group[offset:offset+4];items=[]
                for row in chunk:
                    q=agent._to_internal(row['question'])
                    ids,markers=build_sequence(agent.tok,row['state'],q,agent.cfg['max_len'],agent.cfg['head_max_len'])
                    if len(markers)!=len(q['crit']): raise ValueError('Truncated options')
                    items.append([dict(ids=ids,markers=markers,qtype=0)])
                b=collate_items(items,agent.tok.pad_token_id)
                with torch.no_grad():
                    logits=agent.model(*(b[k].to(agent.device) for k in ('input_ids','attention_mask','marker_pos','marker_mask','qtype')))[0].float().cpu().numpy()
                for row,z in zip(chunk,logits):
                    keys=list(row['question']['criteria']);k=len(keys)
                    temperature=agent.temperature_by_options.get(temp_bucket(0,k),agent.temperature[0])
                    z=z[:k]/max(1e-3,float(temperature));prob=np.exp(z-z.max());prob=prob/prob.sum()
                    cached.append(dict(probabilities={key:round(float(v),4) for key,v in zip(keys,prob)}))
                if offset%200==0: print('CACHE',split,offset,len(group),flush=True)
            cache['answers'][split]=cached
        # Confirm cache computations agree with actual public Agent.predict.
        differences=[]
        for split,group in rows.items():
            for index in np.linspace(0,len(group)-1,6,dtype=int):
                row=group[index];answer=agent.predict(row['state'],{'command':row['question']})['answers']['command']
                differences.append(max(abs(v-cache['answers'][split][index]['probabilities'][k]) for k,v in answer['probabilities'].items()))
        cache['api_probability_max_difference']=max(differences)
        if max(differences)>0.001: raise ValueError('Batched semantic cache differs from runtime')
        a.cache.write_text(json.dumps(cache,indent=2)+'\n')
        del agent
        if a.device=='mps': torch.mps.empty_cache()
    names=sorted({name for row in rows['train'] for name in item_distances(row['state'])})
    prepared={}
    for split,group in rows.items():
        x=torch.tensor([features(row,names) for row in group],dtype=torch.float32)
        b=torch.tensor([semantic_logits(answer) for answer in cache['answers'][split]],dtype=torch.float32)
        mask=torch.tensor([[action in row['question']['criteria'] for action in ACTIONS] for row in group])
        y=torch.tensor([ACTIONS.index(row['label']) for row in group])
        prepared[split]=(x,b,mask,y)
    augmentation_report=None
    if a.augmentation:
        import re
        from training.numeric_augmentation import examples
        categories={name:category for row in rows['train'] for category,line in [(line.split()[1],line) for line in row['state'].splitlines() if line.startswith('Reachable ') and ' items:' in line] for name in item_distances(line)}
        from training.route_survival import labels as survival_labels
        from training.route_priority import labels as route_labels
        from training.route_resupply import labels as resupply_labels
        if sum((a.resupply_labels,a.survival_labels,a.close_health_labels,a.visible_fight_labels,a.finish_route_labels))>1:raise ValueError('Choose one rubric')
        from training.route_resupply_close_health import labels as close_health_labels
        from training.route_visible_resupply import labels as visible_fight_labels
        from training.route_finish import labels as finish_labels
        labeler=finish_labels if a.finish_route_labels else visible_fight_labels if a.visible_fight_labels else close_health_labels if a.close_health_labels else resupply_labels if a.resupply_labels else survival_labels if a.survival_labels else route_labels
        generated={}
        for split,count,seed in [('train',a.augmentation,271900),('synthetic_validation',max(1000,a.augmentation//8),271901)]:
            group=list(examples(categories,count,seed,labeler,broad_inventory=a.wide_inventory,broad_mechanisms=a.wide_mechanisms))
            x=torch.tensor([features(row,names) for row in group],dtype=torch.float32)
            # Deliberately vary semantic priors independently of synthetic facts.
            # These are augmentation noise, not claimed encoder outputs.
            b=prepared['train'][1][torch.randint(len(prepared['train'][1]),(len(group),))].clone()
            mask=torch.tensor([[action in row['question']['criteria'] for action in ACTIONS] for row in group])
            y=torch.tensor([ACTIONS.index(row['label']) for row in group])
            generated[split]=(x,b,mask,y)
        original=prepared['train']
        prepared['train']=tuple(torch.cat([t.repeat((6,1) if t.ndim==2 else (6,)),extra]) for t,extra in zip(original,generated['train']))
        prepared['synthetic_validation']=generated['synthetic_validation']
        augmentation_report=dict(training_rows=len(generated['train'][0]),validation_rows=len(generated['synthetic_validation'][0]),training_seed=271900,validation_seed=271901,
            generator_sha256=digest('training/numeric_augmentation.py'),labeler_sha256=digest(sys.modules[labeler.__module__].__file__),close_health_labels=a.close_health_labels,visible_fight_labels=a.visible_fight_labels,finish_route_labels=a.finish_route_labels,labeler_source_sha256={name:digest(name) for name in (['training/route_finish.py','training/route_visible_resupply.py','training/route_resupply_close_health.py','training/route_resupply.py'] if a.finish_route_labels else ['training/route_visible_resupply.py','training/route_resupply_close_health.py','training/route_resupply.py'] if a.visible_fight_labels else ['training/route_resupply_close_health.py','training/route_resupply.py'] if a.close_health_labels else [sys.modules[labeler.__module__].__file__])},survival_labels=a.survival_labels,resupply_labels=a.resupply_labels,wide_inventory=a.wide_inventory,wide_mechanisms=a.wide_mechanisms,
            semantic_prior='Random frozen real priors independent of synthesized physical values; intentional augmentation noise',real_train_repeat=6)
    thresholds={}
    for index in range(prepared['train'][0].shape[1]):
        unique=prepared['train'][0][:,index].unique().sort().values
        if len(unique)>3: thresholds[str(index)]=torch.quantile(unique,torch.linspace(0,1,min(64 if a.augmentation else 25,len(unique)))).tolist()
    spec=dict(format=FUSION_FORMAT if a.augmentation else FORMAT,feature_format=FEATURE_FORMAT,input_projection=STABLE_FORMAT,actions=list(ACTIONS),
              item_names=names,feature_names=feature_names(names),thresholds=thresholds,hidden_size=192,probability_floor=0.0001)
    loss_weights=torch.ones(len(ACTIONS));loss_weights[ACTIONS.index('exit')]=a.exit_loss_weight
    model=make_residual_model(spec)
    optimizer=torch.optim.AdamW(model.parameters(),lr=0.002,weight_decay=0.0001)
    def evaluate(split='validation'):
        model.eval()
        with torch.no_grad():
            x,b,mask,y=prepared[split];z=model(x,b).masked_fill(~mask,-1e4)
            correct=z.argmax(-1)==y
            return float(correct.float().mean()),correct.tolist()
    initial,_=evaluate();initial_synthetic=evaluate('synthetic_validation')[0] if a.augmentation else initial;best=0.8*initial+0.2*initial_synthetic if a.augmentation else initial;best_epoch=None;history=[];start=time.monotonic()
    for epoch in range(a.epochs):
        model.train();x,b,mask,y=prepared['train']
        for indices in torch.randperm(len(x)).split(512 if a.augmentation else 128):
            z=model(x[indices],b[indices]).masked_fill(~mask[indices],-1e4)
            loss=torch.nn.functional.cross_entropy(z,y[indices],weight=loss_weights);optimizer.zero_grad();loss.backward();optimizer.step()
        score,correct=evaluate();synthetic_score=evaluate('synthetic_validation')[0] if a.augmentation else score
        selection=0.8*score+0.2*synthetic_score if a.augmentation else score
        history.append(dict(epoch=epoch+1,accuracy=score,synthetic_accuracy=synthetic_score,selection=selection))
        if selection>best:
            best=selection;best_accuracy=score;best_synthetic_accuracy=synthetic_score;best_epoch=epoch+1;best_state=copy.deepcopy(model.state_dict());best_correct=correct
        if epoch%25==0: print('EPOCH',epoch+1,'validation',score,'best',best,flush=True)
    if best_epoch is None: raise RuntimeError('No improved validation epoch')
    def clone(source,target):
        if sys.platform=='darwin': subprocess.run(['/bin/cp','-c',str(source),str(target)],check=True)
        else: shutil.copyfile(source,target)
        return target
    shutil.copytree(a.base,a.output,copy_function=clone)
    (a.output/'numeric-residual.json').write_text(json.dumps(spec,indent=2)+'\n')
    save_file({key:value.cpu() for key,value in best_state.items()},str(a.output/'numeric-residual.safetensors'))
    config=json.loads((a.output/'rl_agent_config.json').read_text())
    config['doom_adaptation']['numeric_residual']=dict(format=spec['format'],
        spec_sha256=digest(a.output/'numeric-residual.json'),weights_sha256=digest(a.output/'numeric-residual.safetensors'),
        semantic_parent=a.base.name,semantic_weights_sha256=identity['semantic_weights'],data_sha256=identity['data'],
        seed=771,epochs=a.epochs,exit_loss_weight=a.exit_loss_weight,learning_rate=0.002,batch_size=512 if a.augmentation else 128,augmentation=augmentation_report,threshold_fit='training unique-value quantiles only',
        trainer_sha256=digest(__file__),inference_sha256=digest('doomlib/numeric_command.py'),
        note='Frozen Laya semantic scores plus a learned numeric residual. Correlated development validation, not held-out-map generalization.')
    (a.output/'rl_agent_config.json').write_text(json.dumps(config,indent=2)+'\n')
    total=collections.Counter();correct=collections.Counter()
    for row,ok in zip(rows['validation'],best_correct): total[row['category']]+=1;correct[row['category']]+=ok
    metrics=dict(base_accuracy=initial,best_accuracy=best_accuracy,best_synthetic_accuracy=best_synthetic_accuracy,selection_score=best,semantic_scale=float(best_state.get("semantic_scale",1.0)),best_epoch=best_epoch,seconds=time.monotonic()-start,
        cache_probability_max_difference=cache['api_probability_max_difference'],epochs=history,
        categories={k:dict(correct=correct[k],total=v) for k,v in total.items()},identity=identity)
    (a.output/'training-metrics.json').write_text(json.dumps(metrics,indent=2)+'\n')
    (a.output/'best-epoch.json').write_text(json.dumps(dict(epoch=best_epoch,validation={'command':best_accuracy},numeric_residual=True),indent=2)+'\n')
    archived=a.output/'source'/'training'/'finetune_numeric_residual.py'
    archived.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(__file__,archived)
    print('CHECKPOINT',a.output,'base',initial,'best',best,'epoch',best_epoch,flush=True)

if __name__=='__main__':main()
