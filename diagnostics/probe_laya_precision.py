"""Offline precision parity and timed inference on identical recorded requests."""
import argparse,copy,hashlib,json,os,statistics,sys,time
from pathlib import Path
os.environ['USE_TF']='0';os.environ['USE_TORCH']='1';os.environ['TOKENIZERS_PARALLELISM']='false'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('run',type=Path);p.add_argument('--health',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--cases',type=int,default=30);p.add_argument('--head-checkpoint',action='append',default=[]);a=p.parse_args()
    if a.output.exists():p.error('Output exists')
    import torch
    from laya import Agent
    from doomlib.question_heads import QuestionHeads,load_head,parse_head_specs
    from doomlib.laya_runtime import enable_single_option_padding
    torch.set_num_threads(4)
    health=json.loads(a.health.read_text());metadata=health['question_heads'];root=Path('checkpoints')/metadata['default']['checkpoint'];base=Agent(str(root),device='mps');enable_single_option_padding(base.model)
    overrides={};head_overrides=parse_head_specs(a.head_checkpoint);override_metadata={}
    for name,info in metadata.items():
        if not isinstance(info,dict) or name=='default':continue
        path=Path(head_overrides.get(name,Path('checkpoints')/info['checkpoint']));overrides[name]=load_head(base,root,path)
        if name in head_overrides:
            with (path/'model.safetensors').open('rb') as f:sha=hashlib.file_digest(f,'sha256').hexdigest()
            override_metadata[name]=dict(checkpoint=path.name,weights_sha256=sha)
    inference=QuestionHeads(base,overrides,item_without_goal=True,command_without_goal=True,enemy_without_goal=True)
    rows=[json.loads(l) for l in (a.run/'decisions.jsonl').open()];rows=[r for r in rows if r['directive']['action']=='attack'];indices=sorted({round(i*(len(rows)-1)/(a.cases-1)) for i in range(a.cases)});cases=[rows[i] for i in indices]
    results={}
    def predict(packet):
        qs=packet['questions'];first=inference.predict(packet['state'],{k:qs[k] for k in ('command','weapon')});required=packet['question_dependencies'][first['answers']['command']['choice']];secondary={k:qs[k] for k in required if k not in ('command','weapon')};answer=dict(first['answers'])
        if secondary:answer.update(inference.predict(packet['state'],secondary)['answers'])
        return answer
    for precision,dtype in [('float32',torch.float32),('encoder_bfloat16_head_float32',torch.bfloat16)]:
        base.model.encoder.to(dtype=dtype).eval()
        for row in cases[:3]:predict(row['packet'])
        times=[];answers=[]
        for row in cases:
            torch.mps.synchronize();start=time.perf_counter();ans=predict(row['packet']);torch.mps.synchronize();times.append((time.perf_counter()-start)*1000);answers.append(ans)
        results[precision]=dict(median_ms=statistics.median(times),p90_ms=sorted(times)[int(.9*(len(times)-1))],times_ms=times,answers=answers)
        print(precision,results[precision]['median_ms'],flush=True)
    differences=[];same=0;total=0;max_delta=0
    for row,left,right in zip(cases,results['float32']['answers'],results['encoder_bfloat16_head_float32']['answers']):
        for name in set(left)|set(right):
            total+=1
            if name not in left or name not in right or left[name]['choice']!=right[name]['choice']:differences.append(dict(tick=row['tick'],question=name,float32=left.get(name),bfloat16=right.get(name)))
            else:same+=1
            if name in left and name in right:
                max_delta=max(max_delta,max(abs(left[name]['probabilities'][k]-right[name]['probabilities'][k]) for k in left[name]['probabilities']))
    report=dict(note='Sequential offline benchmark, no gameplay or training should run concurrently. Same recorded inputs and checkpoint tensors, only encoder cast to bfloat16, heads remain float32. Conditional question requests match live client. Finite-case parity is not proof of identical gameplay.',health=health,head_overrides=override_metadata,cases=len(cases),same_choices=same,total_answers=total,max_probability_delta=max_delta,differences=differences,results=results)
    a.output.write_text(json.dumps(report,indent=2));print(dict(cases=len(cases),same_choices=same,total_answers=total,differences=len(differences),max_probability_delta=max_delta))

if __name__=='__main__':main()
