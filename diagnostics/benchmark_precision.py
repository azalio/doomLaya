"""Compare native MPS inference dtypes on identical recorded question packets."""
import os
os.environ['USE_TF']='0'
os.environ['USE_TORCH']='1'
os.environ['TOKENIZERS_PARALLELISM']='false'
import argparse
import copy
import gc
import hashlib
import json
import math
import statistics
import sys
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from doomlib.decision_questions import without_action_continuation
from doomlib.laya_runtime import enable_single_option_padding
from doomlib.model_decoding import ChoiceDecoder


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--checkpoint',type=Path,required=True)
    p.add_argument('--run',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--cases',type=int,default=16)
    p.add_argument('--challenge',type=Path)
    p.add_argument('--dtype',choices=['float32','bfloat16','float16'],default='float32')
    p.add_argument('--baseline',type=Path)
    p.add_argument('--disable-mha-fastpath',action='store_true')
    a=p.parse_args()
    if a.output.exists():p.error('output exists')
    import torch
    from laya import Agent
    torch.set_num_threads(4)
    if a.disable_mha_fastpath:torch.backends.mha.set_fastpath_enabled(False)
    rows=[json.loads(line) for line in (a.run/'decisions.jsonl').open()]
    selected=[rows[round(i*(len(rows)-1)/max(1,a.cases-1))] for i in range(a.cases)]
    packets=[without_action_continuation(copy.deepcopy(d['packet'])) for d in selected]
    challenge=json.loads(a.challenge.read_text()) if a.challenge else []
    results={};baseline=json.loads(a.baseline.read_text())['results']['float32']['answers'] if a.baseline else None
    if a.dtype!='float32' and baseline is None:p.error('non-float32 comparison requires --baseline')
    for name in (a.dtype,):
        model=None
        try:
            model=Agent(str(a.checkpoint),device='mps')
            if model.device.type!='mps':raise RuntimeError('MPS benchmark fell back to another device')
            enable_single_option_padding(model.model)
            model.model.to(dtype=getattr(torch,name));model.model.eval()
            decoder=ChoiceDecoder(0.,0,None)
            for packet in packets[:2]:decoder.apply(model.predict(packet['state'],packet['questions']))
            timing=[];answers=[]
            for packet in packets:
                torch.mps.synchronize();start=time.perf_counter()
                response=decoder.apply(model.predict(packet['state'],packet['questions']))
                torch.mps.synchronize();timing.append((time.perf_counter()-start)*1000)
                for answer in response['answers'].values():
                    probabilities=list(answer['probabilities'].values())
                    if not all(math.isfinite(v) and 0<=v<=1 for v in probabilities) or not math.isclose(sum(probabilities),1,abs_tol=.002):
                        raise ValueError('Invalid probability distribution')
                answers.append({kind:value['choice'] for kind,value in response['answers'].items()})
            if baseline is None:baseline=answers
            differences=[dict(case=i,question=kind,baseline=baseline[i][kind],actual=choice) for i,answer in enumerate(answers) for kind,choice in answer.items() if choice!=baseline[i][kind]]
            challenge_results=[]
            for index,row in enumerate(challenge):
                result=decoder.apply(model.predict(row['state'],{row['kind']:row['question']}))
                answer=result['answers'][row['kind']]
                if not all(math.isfinite(v) for v in answer['probabilities'].values()):raise ValueError('Nonfinite challenge probabilities')
                choice=answer['choice']
                challenge_results.append(dict(index=index,kind=row['kind'],case=row['case'],expected=row['label'],actual=choice,correct=choice==row['label']))
            results[name]=dict(challenge_correct=sum(r['correct'] for r in challenge_results),challenge_results=challenge_results,median_ms=statistics.median(timing),p90_ms=sorted(timing)[int((len(timing)-1)*.9)],latency_ms=timing,answers=answers,changed_choices=differences,questions=sum(len(v) for v in answers))
            print(name,{k:v for k,v in results[name].items() if k not in ('answers','latency_ms','challenge_results')},flush=True)
        except Exception as error:
            results[name]=dict(error=type(error).__name__+': '+str(error));print(name,results[name],flush=True)
        finally:
            del model;gc.collect();torch.mps.empty_cache()
    report=dict(note='Offline native MPS forward-time comparison, without HTTP or gameplay. Dtype casting does not change stored weights; changed answers are reported.',checkpoint=str(a.checkpoint),weights_sha256=hashlib.sha256((a.checkpoint/'model.safetensors').read_bytes()).hexdigest(),torch_version=torch.__version__,mha_fastpath=torch.backends.mha.get_fastpath_enabled(),baseline=str(a.baseline) if a.baseline else None,source_run=str(a.run),challenge=str(a.challenge) if a.challenge else None,challenge_sha256=hashlib.sha256(a.challenge.read_bytes()).hexdigest() if a.challenge else None,ticks=[d['tick'] for d in selected],results=results)
    a.output.write_text(json.dumps(report,indent=2))


if __name__=='__main__':main()
