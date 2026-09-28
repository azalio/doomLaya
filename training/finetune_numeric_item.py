"""Train a numerical item-score residual; the frozen Laya item head still supplies semantic scores."""
import argparse,collections,copy,hashlib,json,math,os,random,shutil,subprocess,sys,time
from pathlib import Path
os.environ.update(USE_TF='0',USE_TORCH='1',TOKENIZERS_PARALLELISM='false')
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from doomlib.numeric_item import FORMAT,CATEGORY_FORMAT,observations,make_model
from training.numeric_augmentation import examples
from doomlib.compact_item import category_item_input
from doomlib.items import WEAPONS
from training.route_priority import labels


def digest(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--base',type=Path,required=True);p.add_argument('--data',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--cache',type=Path,required=True);p.add_argument('--epochs',type=int,default=200);p.add_argument('--augmentation',type=int,default=40000);p.add_argument('--resupply-labels',action='store_true');p.add_argument('--balanced-resupply-labels',action='store_true');a=p.parse_args()
    if a.resupply_labels and a.balanced_resupply_labels:p.error('Choose one rubric')
    if a.balanced_resupply_labels:
        from training.route_resupply_balanced import labels as labeler
    elif a.resupply_labels:
        from training.route_resupply import labels as labeler
    else:labeler=labels
    if a.output.exists():raise ValueError('Output exists')
    import numpy as np
    import torch
    from safetensors.torch import save_file
    from laya import Agent
    from laya.common import build_sequence,collate_items,temp_bucket
    from doomlib.laya_runtime import enable_single_option_padding
    torch.set_num_threads(2);torch.manual_seed(771);random.seed(771)
    rows={s:json.loads((a.data/(s+'.json')).read_text()) for s in ('train','validation')}
    identity=dict(semantic_weights=digest(a.base/'model.safetensors'),config=digest(a.base/'rl_agent_config.json'),data={s:digest(a.data/(s+'.json')) for s in rows})
    if a.cache.exists():
        cache=json.loads(a.cache.read_text())
        if cache['identity']!=identity:raise ValueError('Cache differs')
    else:
        agent=Agent(str(a.base),device='mps');enable_single_option_padding(agent.model);cache=dict(identity=identity,probabilities={})
        for split,group in rows.items():
            result=[]
            for offset in range(0,len(group),4):
                chunk=group[offset:offset+4];items=[]
                for row in chunk:
                    q=agent._to_internal(row['question']);ids,markers=build_sequence(agent.tok,row['state'],q,agent.cfg['max_len'],agent.cfg['head_max_len'])
                    if len(markers)!=len(q['crit']):raise ValueError('Truncated options')
                    items.append([dict(ids=ids,markers=markers,qtype=0)])
                b=collate_items(items,agent.tok.pad_token_id)
                with torch.no_grad():z=agent.model(*(b[k].to(agent.device) for k in ('input_ids','attention_mask','marker_pos','marker_mask','qtype')))[0].float().cpu().numpy()
                for row,z in zip(chunk,z):
                    k=len(row['question']['criteria']);temperature=agent.temperature_by_options.get(temp_bucket(0,k),agent.temperature[0]);z=z[:k]/max(.001,float(temperature));prob=np.exp(z-z.max());prob/=prob.sum();result.append([round(float(v),4) for v in prob])
                if offset%200==0:print('CACHE',split,offset,len(group),flush=True)
            cache['probabilities'][split]=result
        differences=[]
        for split,group in rows.items():
            for i in np.linspace(0,len(group)-1,5,dtype=int):
                answer=agent.predict(group[i]['state'],{'item':group[i]['question']})['answers']['item']
                differences.append(max(abs(v-c) for v,c in zip(answer['probabilities'].values(),cache['probabilities'][split][i])))
        cache['api_probability_max_difference']=max(differences)
        if max(differences)>.001:raise ValueError('Cache/runtime mismatch')
        a.cache.write_text(json.dumps(cache,indent=2)+'\n');del agent;torch.mps.empty_cache()
    categories={text.split()[2]:text.split()[1] for row in rows['train'] for text in row['question']['criteria'].values()};names=sorted(categories)
    prepared={}
    def prepare(group,probabilities=None):
        out=[]
        for i,row in enumerate(group):
            keys=list(row['question']['criteria']);x=observations(row['state'],row['question'],names)
            prob=probabilities[i] if probabilities is not None else np.random.default_rng(991+i).dirichlet(np.ones(len(keys))*.2).tolist()
            out.append((x,[math.log(max(v,.0001)) for v in prob],keys.index(row['label'])))
        return out
    for split,group in rows.items():prepared[split]=prepare(group,cache['probabilities'][split])
    def synthetic(count,seed):
        group=[]
        for row in examples(categories,count,seed,labeler,include_items=True):
            label=row['item_label']
            if label is None:continue
            packet=row['packet'];options={}
            for key,item in packet['targets']['item'].items():
                owned=''
                if item['name'] in WEAPONS:
                    owned='; '+('owned' if packet['observation']['inventory'][str(WEAPONS[item['name']])]['owned'] else 'not owned')
                options[key]=f'{item["name"]}; reachable{owned}; {item["distance"]:.1f}m.'
            state,q=category_item_input(packet['state'],dict(type='choice',instructions='Choose a useful item.',criteria=options))
            group.append(dict(state=state,question=q,label=label))
        return group
    synth={s:synthetic(n,seed) for s,n,seed in [('train',a.augmentation,272000),('synthetic_validation',a.augmentation//8,272001)]}
    prepared['train']=prepared['train']*6+prepare(synth['train']);prepared['synthetic_validation']=prepare(synth['synthetic_validation'])
    observed=torch.tensor([x for row in prepared['train'] for x in row[0]],dtype=torch.float32);thresholds={}
    for i in range(observed.shape[1]):
        unique=observed[:,i].unique().sort().values
        if len(unique)>3:thresholds[str(i)]=torch.quantile(unique,torch.linspace(0,1,min(48,len(unique)))).tolist()
    spec=dict(format=FORMAT,question='item',input_projection=CATEGORY_FORMAT,item_names=names,features=observed.shape[1],thresholds=thresholds,hidden_size=128,probability_floor=.0001)
    del observed
    model=make_model(spec);optimizer=torch.optim.AdamW(model.parameters(),lr=.002,weight_decay=.0001)
    def batch(group):
        n=len(group);k=max(len(r[0]) for r in group);x=torch.zeros(n,k,spec['features']);b=torch.zeros(n,k);mask=torch.zeros(n,k,dtype=torch.bool);y=[]
        for i,(values,base,target) in enumerate(group):
            size=len(values);x[i,:size]=torch.tensor(values);b[i,:size]=torch.tensor(base);mask[i,:size]=True;y.append(target)
        return x,b,mask,torch.tensor(y)
    # Fixed tensor batches avoid repeatedly parsing all numeric rows during fitting.
    tensors={split:batch(group) for split,group in prepared.items()}
    del prepared
    def evaluate(split):
        model.eval();x,b,mask,y=tensors[split];correct=[]
        with torch.no_grad():
            for offset in range(0,len(x),128):correct.extend((model(x[offset:offset+128],b[offset:offset+128]).masked_fill(~mask[offset:offset+128],-1e4).argmax(-1)==y[offset:offset+128]).tolist())
        return sum(correct)/len(correct)
    initial=evaluate('validation');best=.8*initial+.2*evaluate('synthetic_validation');best_epoch=None;history=[];start=time.monotonic()
    for epoch in range(a.epochs):
        model.train();x,b,mask,y=tensors['train']
        for indices in torch.randperm(len(x)).split(128):
            z=model(x[indices],b[indices]).masked_fill(~mask[indices],-1e4);loss=torch.nn.functional.cross_entropy(z,y[indices]);optimizer.zero_grad();loss.backward();optimizer.step()
        score=evaluate('validation');synth_score=evaluate('synthetic_validation');selection=.8*score+.2*synth_score
        history.append(dict(epoch=epoch+1,accuracy=score,synthetic_accuracy=synth_score,selection=selection))
        if selection>best:best=selection;best_epoch=epoch+1;best_state=copy.deepcopy(model.state_dict());best_accuracy=score;best_synthetic=synth_score
        if epoch%20==0:print('EPOCH',epoch+1,'validation',score,'synthetic',synth_score,'best',best,flush=True)
    if best_epoch is None:raise ValueError('No improved epoch')
    def clone(source,target):
        if sys.platform=='darwin':subprocess.run(['/bin/cp','-c',str(source),str(target)],check=True)
        else:shutil.copyfile(source,target)
        return target
    shutil.copytree(a.base,a.output,copy_function=clone)
    (a.output/'numeric-residual.json').write_text(json.dumps(spec,indent=2)+'\n');save_file(best_state,str(a.output/'numeric-residual.safetensors'))
    config=json.loads((a.output/'rl_agent_config.json').read_text());config['doom_adaptation']['numeric_residual']=dict(format=FORMAT,spec_sha256=digest(a.output/'numeric-residual.json'),weights_sha256=digest(a.output/'numeric-residual.safetensors'),semantic_parent=a.base.name,identity=identity,epochs=a.epochs,seed=771,learning_rate=.002,augmentation_rows={k:len(v) for k,v in synth.items()},augmentation_requested=a.augmentation,training_seed=272000,validation_seed=272001,real_train_repeat=6,trainer_sha256=digest(__file__),generator_sha256=digest('training/numeric_augmentation.py'),resupply_labels=a.resupply_labels,balanced_resupply_labels=a.balanced_resupply_labels,labeler_sha256=digest(sys.modules[labeler.__module__].__file__),labeler_source_sha256={name:digest(name) for name in (['training/route_resupply_balanced.py','training/route_resupply.py','training/build_map3_resources.py'] if a.balanced_resupply_labels else [sys.modules[labeler.__module__].__file__])},inference_sha256=digest('doomlib/numeric_item.py'),note='Random semantic priors on synthetic observations are deliberate augmentation noise, not encoder outputs. Correlated same-map development validation.')
    (a.output/'rl_agent_config.json').write_text(json.dumps(config,indent=2)+'\n')
    metrics=dict(base_accuracy=initial,best_accuracy=best_accuracy,best_synthetic_accuracy=best_synthetic,best_epoch=best_epoch,semantic_scale=float(best_state['semantic_scale']),seconds=time.monotonic()-start,epochs=history,cache_probability_max_difference=cache['api_probability_max_difference'])
    (a.output/'training-metrics.json').write_text(json.dumps(metrics,indent=2)+'\n');(a.output/'best-epoch.json').write_text(json.dumps(dict(epoch=best_epoch,validation={'item':best_accuracy},numeric_residual=True),indent=2)+'\n')
    print('CHECKPOINT',a.output,'accuracy',best_accuracy,'synthetic',best_synthetic,'epoch',best_epoch,flush=True)

if __name__=='__main__':main()
